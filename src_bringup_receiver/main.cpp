#include <SPI.h>
#include <mcp_can.h>

#define CAN_INT 2
MCP_CAN CAN0(10);

// Timestamp captured in the ISR the moment INT goes low
volatile unsigned long isrTime = 0;
volatile bool frameFlag = false;
volatile unsigned int lostFlags = 0;   // INT fired again before the previous frame was handled

void canISR() {
  if (frameFlag) lostFlags++;   // previous timestamp not consumed yet
  isrTime = micros();
  frameFlag = true;
}

void setup() {
  Serial.begin(115200);
  pinMode(CAN_INT, INPUT);

  if (CAN0.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) != CAN_OK) {
    Serial.println("init FAILED"); while (1);
  }
  CAN0.setMode(MCP_NORMAL);   // keep normal mode for now so the sender gets ACKs
  attachInterrupt(digitalPinToInterrupt(CAN_INT), canISR, FALLING);
  Serial.println("Receiver ready");
  Serial.println("id,micros");
}

void loop() {
  if (!frameFlag) return;

  // Copy the timestamp atomically, then clear the flag
  noInterrupts();
  unsigned long t = isrTime;
  frameFlag = false;
  interrupts();

  // Drain every frame waiting in the MCP2515 buffers
  while (CAN0.checkReceive() == CAN_MSGAVAIL) {
    unsigned long id; byte len; byte rx[8];
    CAN0.readMsgBuf(&id, &len, rx);
    Serial.print("0x"); Serial.print(id, HEX);
    Serial.print(',');  Serial.println(t);
  }
}