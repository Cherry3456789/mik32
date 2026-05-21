#include <stdint.h>
#include <string.h>
#include "protocol.h"
#include "transport_serial.h"
#include "tinyml_runtime.h"

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

            uint8_t outbuf[64] = {0};
            uint16_t outlen = sizeof(outbuf);
            if (!tinyml_infer(test_vec, copy, outbuf, &outlen)) {
                send_simple(MSG_NACK, in.seq);
                continue;
            }

            frame_t out = {0};
            out.type = MSG_INFER_RESULT;
            out.seq = in.seq;
            out.len = outlen;
            memcpy(out.payload, outbuf, outlen);
            uint8_t raw[1200] = {0};
            uint16_t raw_len = 0;
            frame_encode(&out, raw, &raw_len);
            transport_write(raw, raw_len);
            send_simple(MSG_FINISH, in.seq);
        }
    }
}
