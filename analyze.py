#!/usr/bin/env python3
"""CIDS analysis for the CAN prototype (Cho & Shin, USENIX Security 2016).

Usage:
    python analyze.py capture.csv                  # all IDs found in the capture
    python analyze.py capture.csv --only 0x11,0x55
    python analyze.py capture.csv --guard 0        # disable collision filter
"""
import argparse
import numpy as np
import matplotlib.pyplot as plt

# ---- Parameters (paper values where given) --------------------------------
N        = 20          # messages per estimation step
KAPPA    = 5.0         # CUSUM kappa
GAMMA_L  = 5.0         # CUSUM threshold
T_NOM    = 50000.0     # nominal period [us] of all test messages
SETTLE   = 10          # first errors are a start-up transient: ignore them
WARM     = 40          # batches used to learn the CUSUM target values
TRACK_L  = 0.99        # forgetting of the increment tracker
RATE_BIN = 5.0         # seconds per bin in the message-rate panel
A_IDS    = (0x11, 0x13)   # sent by node A
B_IDS    = (0x55,)        # sent by node B
COLORS   = {0x11: "tab:blue", 0x13: "tab:green", 0x55: "tab:orange"}


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
    d = np.diff(ts) % (1 << 32)                 # unwrap 32-bit micros()
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


def drop_collisions(ids, t, guard):
    if guard <= 0:
        return ids, t
    isA = np.isin(ids, A_IDS)
    isB = np.isin(ids, B_IDS)
    near = np.zeros(len(t), bool)
    near[isA] = near_other(t[isA], t[isB], guard)
    near[isB] = near_other(t[isB], t[isA], guard)
    return ids[~near], t[~near]


# ---- Algorithm 1 ----------------------------------------------------------
def frame_index(a, T=T_NOM):
    steps = np.maximum(np.round(np.diff(a) / T), 1)
    return np.concatenate([[0], np.cumsum(steps)])


def accumulated_offset(a, idx, T=T_NOM):
    acc, tvalid = 0.0, 0.0
    t_real, t_val, oacc = [], [], []
    i = np.arange(1, N)
    for k in range(len(a) // N):
        s = k * N
        if idx[s + N - 1] - idx[s] != N - 1:      # window contains a cut
            continue
        w = a[s:s + N]
        ok = np.mean(w[1:] - (w[0] + i * T))
        acc += abs(ok)
        tvalid += N * T / 1e6
        t_real.append((w[0] - a[0]) / 1e6)
        t_val.append(tvalid)
        oacc.append(acc)
    return np.array(t_real), np.array(t_val), np.array(oacc)


def track(inc, lam=TRACK_L, init=10):
    """Running estimate of the per-window offset increment; error = new - estimate."""
    S = np.mean(inc[:init])
    s, e = np.zeros(len(inc)), np.zeros(len(inc))
    for k, x in enumerate(inc):
        e[k] = x - S
        if k >= init:
            S = lam * S + (1 - lam) * x
        s[k] = S
    return s, e


def cusum(e, kappa=KAPPA, gamma=GAMMA_L, settle=SETTLE, warm=WARM):
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
    t_end = t[-1] / 1e6
    print(f"loaded {len(ids)} frames, {t_end:.0f} s")

    all_ids = sorted(set(ids))
    use = [int(x, 16) for x in args.only.split(",") if x] or all_ids

    # raw report: gaps and suspension per ID
    suspended = {}
    for mid in all_ids:
        a = t[ids == mid]
        bad = np.sum(np.abs(np.diff(a) - T_NOM) > 5000)
        silent = (t[-1] - a[-1]) / 1e6
        print(f"0x{mid:X}: {len(a)} frames, {bad} abnormal intervals (raw)")
        if silent > 1.0:                                  # > 1 s without a frame at the end
            suspended[mid] = a[-1] / 1e6
            print(f"   >>> SUSPENSION detected: last frame at t={a[-1] / 1e6:.1f} s, "
                  f"silent for {silent:.0f} s")
            

    ids_f, t_f = drop_collisions(ids, t, args.guard)
    print(f"collision filter removed {len(ids) - len(ids_f)} frames "
          f"({100 * (len(ids) - len(ids_f)) / len(ids):.1f} %)\n")

    fig, ax = plt.subplots(4, 1, figsize=(10, 12), sharex=True)

    # panel 4: frames per second per ID (raw data) -> suspension = 0, fabrication = 2x
    bins = np.arange(0, t_end + RATE_BIN, RATE_BIN)
    for mid in use:
        cnt, _ = np.histogram(t[ids == mid] / 1e6, bins=bins)
        ax[3].step(bins[:-1], cnt / RATE_BIN, where="post",
                   color=COLORS.get(mid), label=f"0x{mid:X}")
    ax[3].set_ylabel("Frames per second")
    ax[3].set_xlabel("Time [s]")
    ax[3].legend()

    for mid in use:
        name, col = f"0x{mid:X}", COLORS.get(mid)
        a = t_f[ids_f == mid]
        if len(a) < 3 * N:
            print(f"{name}: too few frames, skipped")
            continue
        idx = frame_index(a)

        period = np.polyfit(idx, a, 1)[0]
        ppm = (period - T_NOM) / T_NOM * 1e6

        t_real, t_val, oacc = accumulated_offset(a, idx)
        inc = np.diff(oacc, prepend=0.0)
        _, e = track(inc)
        lp, lm, alarm = cusum(e)

        alarm_txt = "none" if alarm is None else f"batch {alarm} (t={t_real[alarm]:.0f} s)"
        print(f"{name}: period {period:.2f} us -> {ppm:+.1f} ppm vs R | CUSUM alarm: {alarm_txt}")

        ax[0].plot(t_real, oacc, color=col, label=f"{name} ({ppm:+.0f} ppm)")
        ax[1].plot(t_real, e, color=col, label=name)
        ax[2].plot(t_real, lp, color=col, label=f"L+ {name}")
        ax[2].plot(t_real, lm, "--", color=col, label=f"L- {name}")
        if alarm is not None:
            ax[2].axvline(t_real[alarm], color=col, alpha=0.4)

    # mark suspensions in every panel
    for mid, ts in suspended.items():
        for x in ax:
            x.axvline(ts, color=COLORS.get(mid, "purple"), ls=":", lw=2)
        ax[0].annotate(f"0x{mid:X} suspended", (ts, ax[0].get_ylim()[1] * 0.9),
                       rotation=90, va="top", ha="right", fontsize=8)

    ax[0].set_ylabel("Accum. clock offset [us]"); ax[0].legend()
    ax[1].set_ylabel("Identification error"); ax[1].legend()
    ax[2].axhline(GAMMA_L, ls="--", c="k")
    ax[2].set_ylabel("CUSUM L+ / L-"); ax[2].legend(ncol=2, fontsize=8)
    plt.tight_layout()
    plt.savefig(args.save, dpi=130)
    print(f"\nplot saved to {args.save}")
    plt.show()


if __name__ == "__main__":
    main()