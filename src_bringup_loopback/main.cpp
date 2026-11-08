#include <SPI.h>
#include <mcp_can.h>

#define CAN_CS  10
#define CAN_INT 2

MCP_CAN CAN0(CAN_CS);

void setup() {
  Serial.begin(115200);
  pinMode(CAN_INT, INPUT);

  if (CAN0.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) == CAN_OK)
    Serial.println("MCP2515 init OK");
  else {
    Serial.println("MCP2515 init FAILED");
    while (1);
  }
  CAN0.setMode(MCP_LOOPBACK);   // frames are looped back internally
  Serial.println("Loopback mode");
}

void loop() {
  byte txData[8] = {1, 2, 3, 4, 5, 6, 7, 8};
  byte st = CAN0.sendMsgBuf(0x11, 0, 8, txData);
  Serial.print("send: ");
  Serial.println(st == CAN_OK ? "OK" : "ERROR");

  delay(10);
  Serial.print("INT pin (expect 0 = LOW): ");
  Serial.println(digitalRead(CAN_INT));

  if (CAN0.checkReceive() == CAN_MSGAVAIL) {
    unsigned long id; byte len; byte rx[8];
    CAN0.readMsgBuf(&id, &len, rx);
    Serial.print("rx id=0x"); Serial.print(id, HEX);
    Serial.print(" len="); Serial.print(len);
    Serial.print(" data=");
    for (byte i = 0; i < len; i++) { Serial.print(rx[i]); Serial.print(' '); }
    Serial.println();
  } else {
    Serial.println("nothing received");
  }
  Serial.println();
  delay(1000);
}