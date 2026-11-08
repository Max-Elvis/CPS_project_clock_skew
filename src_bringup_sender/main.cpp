#include <SPI.h>
#include <mcp_can.h>

MCP_CAN CAN0(10);
byte counter = 0;

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  if (CAN0.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) != CAN_OK) {
    Serial.println("init FAILED"); while (1);
  }
  CAN0.setMode(MCP_NORMAL);
  Serial.println("Sender ready");
}

void loop() {
  byte data[8] = {counter, 0, 0, 0, 0, 0, 0, 0};
  byte st = CAN0.sendMsgBuf(0x11, 0, 8, data);
  Serial.print("tx #"); Serial.print(counter);
  Serial.println(st == CAN_OK ? " OK" : " ERROR");
  counter++;
  digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
  delay(500);
}