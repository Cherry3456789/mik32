#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>

#define FRAME_START 0xAA

typedef enum {
    MSG_HELLO = 0x01,
    MSG_TEST_META = 0x02,
    MSG_TEST_CHUNK = 0x03,
    MSG_INFER_RESULT = 0x04,
    MSG_ACK = 0x05,
    MSG_NACK = 0x06,
    MSG_FINISH = 0x07,
} msg_type_t;

typedef struct {
    uint8_t type;
    uint16_t seq;
    uint16_t len;
    uint8_t payload[MAX_TEST_VECTOR_BYTES];
} frame_t;

uint16_t crc16_ccitt(const uint8_t *data, uint16_t len);
bool frame_encode(const frame_t *in, uint8_t *out, uint16_t *out_len);
bool frame_decode(const uint8_t *in, uint16_t in_len, frame_t *out);

#endif
