#include <stdint.h>
#include <string.h>
#include "protocol.h"
#include "transport_serial.h"
#include "tinyml_runtime.h"

extern uint32_t mik32_millis(void);

static void send_simple(uint8_t type, uint16_t seq) {
    frame_t out = {0};
    out.type = type;
    out.seq = seq;
    out.len = 0;
    uint8_t raw[16];
    uint16_t raw_len = 0;
    frame_encode(&out, raw, &raw_len);
    transport_write(raw, raw_len);
}

int main(void) {
    transport_init();
    static const uint8_t banner[] = "MIK32_TINYML_READY\r\n";
    transport_write(banner, (uint16_t)(sizeof(banner) - 1));

    tinyml_shape_t shape = {0};
    if (!tinyml_init(&shape)) {
        while (1) {}
    }

    uint8_t rx[1200];
    uint16_t rx_len = 0;
    uint8_t test_vec[MAX_TEST_VECTOR_BYTES];
    uint16_t test_len = 0;

    while (1) {
        if (!transport_read_frame(rx, &rx_len, PROTO_TIMEOUT_MS)) {
            transport_write(banner, (uint16_t)(sizeof(banner) - 1));
            continue;
        }
        frame_t in = {0};
        if (!frame_decode(rx, rx_len, &in)) {
            send_simple(MSG_NACK, 0);
            continue;
        }

        if (in.type == MSG_HELLO) {
            send_simple(MSG_ACK, in.seq);
        } else if (in.type == MSG_TEST_META) {
            if (in.len >= 2) {
                test_len = (uint16_t)(in.payload[0] | (in.payload[1] << 8));
                if (test_len > MAX_TEST_VECTOR_BYTES) test_len = MAX_TEST_VECTOR_BYTES;
                send_simple(MSG_ACK, in.seq);
            } else {
                send_simple(MSG_NACK, in.seq);
            }
        } else if (in.type == MSG_TEST_CHUNK) {
            uint16_t copy = in.len;
            if (copy > test_len) copy = test_len;
            memcpy(test_vec, in.payload, copy);

            uint8_t logits[64] = {0};
            uint16_t logits_len = sizeof(logits);
            uint32_t t0 = mik32_millis();
            if (!tinyml_infer(test_vec, copy, logits, &logits_len)) {
                send_simple(MSG_NACK, in.seq);
                continue;
            }
            uint32_t duration_us = (mik32_millis() - t0) * 1000u;

            frame_t out = {0};
            out.type = MSG_INFER_RESULT;
            out.seq = in.seq;
            out.len = (uint16_t)(4u + logits_len);
            out.payload[0] = (uint8_t)(duration_us & 0xFFu);
            out.payload[1] = (uint8_t)((duration_us >> 8) & 0xFFu);
            out.payload[2] = (uint8_t)((duration_us >> 16) & 0xFFu);
            out.payload[3] = (uint8_t)((duration_us >> 24) & 0xFFu);
            memcpy(&out.payload[4], logits, logits_len);
            uint8_t raw[1200] = {0};
            uint16_t raw_len = 0;
            frame_encode(&out, raw, &raw_len);
            transport_write(raw, raw_len);
            send_simple(MSG_FINISH, in.seq);
        }
    }
}