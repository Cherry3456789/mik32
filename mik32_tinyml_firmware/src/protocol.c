#include "protocol.h"

uint16_t crc16_ccitt(const uint8_t *data, uint16_t len) {
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (uint8_t b = 0; b < 8; b++) {
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
        }
    }
    return crc;
}

bool frame_encode(const frame_t *in, uint8_t *out, uint16_t *out_len) {
    if (!in || !out || !out_len) return false;
    uint16_t total = (uint16_t)(1 + 1 + 2 + 2 + in->len + 2);
    out[0] = FRAME_START;
    out[1] = in->type;
    out[2] = (uint8_t)(in->seq & 0xFF);
    out[3] = (uint8_t)(in->seq >> 8);
    out[4] = (uint8_t)(in->len & 0xFF);
    out[5] = (uint8_t)(in->len >> 8);
    for (uint16_t i = 0; i < in->len; i++) out[6 + i] = in->payload[i];
    uint16_t crc = crc16_ccitt(&out[1], (uint16_t)(1 + 2 + 2 + in->len));
    out[6 + in->len] = (uint8_t)(crc & 0xFF);
    out[7 + in->len] = (uint8_t)(crc >> 8);
    *out_len = total;
    return true;
}

bool frame_decode(const uint8_t *in, uint16_t in_len, frame_t *out) {
    if (!in || !out || in_len < 8 || in[0] != FRAME_START) return false;
    out->type = in[1];
    out->seq = (uint16_t)(in[2] | (in[3] << 8));
    out->len = (uint16_t)(in[4] | (in[5] << 8));
    if (out->len > MAX_TEST_VECTOR_BYTES || in_len < (uint16_t)(8 + out->len - 0)) return false;
    for (uint16_t i = 0; i < out->len; i++) out->payload[i] = in[6 + i];
    uint16_t got = (uint16_t)(in[6 + out->len] | (in[7 + out->len] << 8));
    uint16_t exp = crc16_ccitt(&in[1], (uint16_t)(1 + 2 + 2 + out->len));
    return got == exp;
}
