#!/usr/bin/env python3
"""CIDS analysis for the CAN prototype (Cho & Shin, USENIX Security 2016).

Usage:
    python analyze.py capture.csv                  # all IDs in the capture
    python analyze.py capture.csv --only 0x11,0x55
    python analyze.py capture.csv --guard 0        # disable collision filter
"""
import argparse
import numpy as np
import matplotlib.pyplot as plt

# ---- Parameters -----------------------------------------------------------
N        = 20            # messages per estimation step (paper)
KAPPA    = 5.0           # CUSUM kappa (paper)
GAMMA_L  = 5.0           # CUSUM threshold (paper)
T_NOM    = 50000.0       # nominal period [us]
SETTLE   = 10            # start-up batches to ignore
WARM     = 40            # batches used to learn the CUSUM target values
TRACK_L  = 0.99          # forgetting factor of the increment tracker
A_IDS    = (0x11, 0x13)  # sent by node A
B_IDS    = (0x55,)       # sent by node B
COLORS   = {0x11: "tab:blue", 0x13: "tab:green", 0x55: "tab:orange"}

# gap sizes (in multiples of T_NOM) treated as a masquerade handover rather
# than ordinary jitter (lower) or an end-of-capture suspension (upper, s)
MASQ_GAP_MIN = 1.4
MASQ_GAP_MAX = 20.0
SUSPEND_S    = 1.0


# ---- Loading --------------------------------------------------------------
def load(path):
    ids, ts = [], []
    for line in open(path):
        parts = line.strip().split(",")
        if len(parts) != 2:
            continue
        try:
            ids.append(int(parts[0], 16))
            ts.append(int(parts[1]))
        except ValueError:
            continue
    ids = np.array(ids)
    ts = np.array(ts, dtype=np.int64)
    d = np.diff(ts) % (1 << 32)                  # unwrap 32-bit micros()
    t = np.concatenate([[0], np.cumsum(d)]).astype(float)
    return ids, t


# ---- Collision filter (bus-busy check, paper Sec. 4.4) --------------------
def near_other(a, b, guard):
    if len(b) == 0:
        return np.zeros(len(a), bool)
    j = np.searchsorted(b, a)
    left = np.abs(a - b[np.clip(j - 1, 0, len(b) - 1)])
    right = np.abs(a - b[np.clip(j, 0, len(b) - 1)])
    return np.minimum(left, right) < guard


def drop_collisions(ids, t, guard, t_fab=np.inf, t_masq=np.inf):
    """Drop frames delayed by arbitration at the A/B crossings. 0x11 is left
    untouched once a fabrication has started, and the filter switches off
    entirely once a masquerade handover has happened (0x55 then shares A's
    tick permanently, so every later 0x55 frame would otherwise be dropped)."""
    if guard <= 0:
        return ids, t
    is11, is13, is55 = ids == 0x11, ids == 0x13, ids == 0x55
    isA = is11 | is13
    near = np.zeros(len(t), bool)
    near[isA] = near_other(t[isA], t[is55], guard)
    near[is55] = near_other(t[is55], t[is13], guard)
    near[is11 & (t / 1e6 >= t_fab - 1.0)] = False
    near[t / 1e6 >= t_masq - 1.0] = False
    return ids[~near], t[~near]


def frame_index(a, T=T_NOM):
    steps = np.maximum(np.round(np.diff(a) / T), 1)
    return np.concatenate([[0], np.cumsum(steps)])


def accumulated_offset(a, idx, T=T_NOM):
    acc, tvalid = 0.0, 0.0
    t_real, oacc = [], []
    i = np.arange(1, N)
    for k in range(len(a) // N):
        s = k * N
        if idx[s + N - 1] - idx[s] != N - 1:      # window contains a cut
            continue
        w = a[s:s + N]
        acc += abs(np.mean(w[1:] - (w[0] + i * T)))
        t_real.append((w[0] - a[0]) / 1e6)
        oacc.append(acc)
    return np.array(t_real), np.array(oacc)


def track(inc, lam=TRACK_L, init=10):
    """Running estimate of the per-window offset increment; error = new - estimate.
    This is a simple exponential moving average to counter the random clock jitter/drift"""
    S = np.mean(inc[:init])
    e = np.zeros(len(inc))
    for k, x in enumerate(inc):
        e[k] = x - S
        if k >= init:
            S = lam * S + (1 - lam) * x
    return e


def cusum(e, kappa=KAPPA, gamma=GAMMA_L, settle=SETTLE, warm=WARM):
    """The CUSUM algorithm presented in the paper (Sec. 4.3). Returns the L+ and L- sequences, and the index of the first alarm (or None)."""
    n = len(e)
    lp, lm = np.zeros(n), np.zeros(n)
    alarm = None
    if n <= warm:
        return lp, lm, alarm
    base = np.asarray(e[settle:warm])
    mu, var, cnt = base.mean(), max(base.var(), 1e-6), len(base)
    Lp = Lm = 0.0
    for k in range(warm, n):
        z = (e[k] - mu) / np.sqrt(var)
        if abs(z) < 3:
            cnt += 1
            d = e[k] - mu
            mu += d / cnt
            var += (d * (e[k] - mu) - var) / cnt
        Lp = max(0.0, Lp + z - kappa)
        Lm = max(0.0, Lm - z - kappa)
        lp[k], lm[k] = Lp, Lm
        if alarm is None and (Lp > gamma or Lm > gamma):
            alarm = k
    return lp, lm, alarm


# ---- Main -----------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--only", default="", help="comma-separated IDs, e.g. 0x11,0x55")
    ap.add_argument("--guard", type=float, default=800, help="collision guard in us (0 = off)")
    ap.add_argument("--save", default="cids_plots.png")
    args = ap.parse_args()

    ids, t = load(args.csv)
    print(f"loaded {len(ids)} frames, {t[-1] / 1e6:.0f} s")

    all_ids = sorted(set(ids))
    use = [int(x, 16) for x in args.only.split(",") if x] or all_ids

    # ---- terminal checks ----------------------------
    suspended, fabricated, masq = {}, {}, {}
    for mid in all_ids:
        a = t[ids == mid]
        d = np.diff(a)
        n_abn = int(np.sum(np.abs(d - T_NOM) > 5000))
        print(f"0x{mid:X}: {len(a)} frames, {n_abn} abnormal intervals")

        silent = (t[-1] - a[-1]) / 1e6
        if silent > SUSPEND_S:
            suspended[mid] = a[-1] / 1e6
            print(f"   >>> SUSPENSION: last frame at t={a[-1] / 1e6:.1f} s, silent for {silent:.0f} s")

        n_short = int(np.sum(d < 0.8 * T_NOM))
        if n_short > 20:
            first = a[np.where(d < 0.8 * T_NOM)[0][0]] / 1e6
            fabricated[mid] = first
            print(f"   >>> FABRICATION suspected: {n_short} intervals < 40 ms, first at t={first:.1f} s")

        gaps = np.where((d > MASQ_GAP_MIN * T_NOM) & (d < MASQ_GAP_MAX * T_NOM))[0]
        if len(gaps) and mid not in suspended:
            g = gaps[0]
            pre, post = a[:g + 1], a[g + 1:]
            if len(pre) > 3 * N and len(post) > 3 * N:
                p1 = (np.polyfit(frame_index(pre), pre, 1)[0] - T_NOM) / T_NOM * 1e6
                p2 = (np.polyfit(frame_index(post), post, 1)[0] - T_NOM) / T_NOM * 1e6
                masq[mid] = a[g] / 1e6
                print(f"   >>> MASQUERADE suspected: {d[g] / 1000:.0f} ms gap at t={a[g] / 1e6:.1f} s, "
                      f"skew {p1:+.1f} -> {p2:+.1f} ppm")
            else:
                print(f"   (gap of {d[g] / 1000:.0f} ms at t={a[g] / 1e6:.1f} s too close to an "
                      f"edge to fit skews on both sides, not reported as masquerade)")

    t_fab = min(fabricated.values(), default=np.inf)
    t_masq = min(masq.values(), default=np.inf)
    ids_f, t_f = drop_collisions(ids, t, args.guard, t_fab, t_masq)
    print(f"collision filter removed {len(ids) - len(ids_f)} frames "
          f"({100 * (len(ids) - len(ids_f)) / len(ids):.1f} %)\n")

    fig, ax = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

    for mid in use:
        name, col = f"0x{mid:X}", COLORS.get(mid)
        a = t_f[ids_f == mid]
        if len(a) < 3 * N:
            print(f"{name}: too few frames, skipped")
            continue
        idx = frame_index(a)
        pre = a[a / 1e6 < min(fabricated.get(mid, np.inf), masq.get(mid, np.inf))]
        if len(pre) < 3 * N:
            print(f"{name}: not enough pre-attack data for a skew estimate, skipped")
            continue
        period = np.polyfit(frame_index(pre), pre, 1)[0]
        ppm = (period - T_NOM) / T_NOM * 1e6

        t_real, oacc = accumulated_offset(a, idx)
        e = track(np.diff(oacc, prepend=0.0))
        lp, lm, alarm = cusum(e)

        alarm_txt = "none" if alarm is None else f"batch {alarm} (t={t_real[alarm]:.0f} s)"
        print(f"{name}: {ppm:+.1f} ppm vs R | CUSUM alarm: {alarm_txt}")

        ax[0].plot(t_real, oacc, color=col, label=f"{name} ({ppm:+.0f} ppm)")
        ax[1].plot(t_real, e, color=col, label=name)
        ax[2].plot(t_real, lp, color=col, label=f"L+ {name}")
        ax[2].plot(t_real, lm, "--", color=col, label=f"L- {name}")

    for mid, ts in suspended.items():
        for x in ax:
            x.axvline(ts, color=COLORS.get(mid, "purple"), ls=":", lw=2)

    for mid, ts in fabricated.items():
        for x in ax:
            x.axvline(ts, color=COLORS.get(mid, "red"), ls="-.", lw=2)

    for mid, ts in masq.items():
        for x in ax:
            x.axvline(ts, color=COLORS.get(mid, "red"), ls="--", lw=2)

    ax[0].set_ylabel("Accum. clock offset [us]"); ax[0].legend()
    ax[1].set_ylabel("Identification error"); ax[1].legend()
    ax[2].axhline(GAMMA_L, ls="--", c="k")
    ax[2].set_ylabel("CUSUM L+ / L-"); ax[2].set_xlabel("Time [s]")
    ax[2].legend(ncol=2, fontsize=8)
    plt.tight_layout()
    plt.savefig(args.save, dpi=130)
    print(f"\nplot saved to {args.save}")
    plt.show()


if __name__ == "__main__":
    main()