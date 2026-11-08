#include <SPI.h>
#include <mcp_can.h>

#define CAN_INT 2
MCP_CAN CAN0(10);

void setup() {
  Serial.begin(115200);
  pinMode(CAN_INT, INPUT);
  pinMode(LED_BUILTIN, OUTPUT);
  if (CAN0.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) != CAN_OK) {
    Serial.println("init FAILED"); while (1);
  }
  CAN0.setMode(MCP_NORMAL);
  Serial.println("Receiver ready");
}

void loop() {
  if (!digitalRead(CAN_INT)) {          // INT is active-low when a frame is waiting
    unsigned long id; byte len; byte rx[8];
    CAN0.readMsgBuf(&id, &len, rx);
    Serial.print("rx id=0x"); Serial.print(id, HEX);
    Serial.print(" counter="); Serial.println(rx[0]);
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
  }
}