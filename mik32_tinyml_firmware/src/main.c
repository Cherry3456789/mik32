#include <stdint.h>
#include <string.h>
#include "protocol.h"
#include "transport_serial.h"
#include "tinyml_runtime.h"

extern uint32_t mik32_millis(void);

static uint8_t rx_buf[1200];
static frame_t frame_in;

static void send_simple(uint8_t type, uint16_t seq) {
    uint8_t raw[8];
    raw[0] = FRAME_START;
    raw[1] = type;
    raw[2] = (uint8_t)(seq & 0xFFu);
    raw[3] = (uint8_t)(seq >> 8);
    raw[4] = 0;
    raw[5] = 0;
    uint16_t crc = crc16_ccitt(&raw[1], 5);
    raw[6] = (uint8_t)(crc & 0xFFu);
    raw[7] = (uint8_t)(crc >> 8);
    transport_write(raw, sizeof(raw));
}

int main(void) {
    transport_init();
    static const uint8_t banner[] = "MIK32_TINYML_READY\r\n";
    transport_write(banner, (uint16_t)(sizeof(banner) - 1));

    tinyml_shape_t shape = {0};
    if (!tinyml_init(&shape)) {
        while (1) {}
    }

    uint16_t rx_len = 0;
    uint16_t test_len = 0;

    while (1) {
        if (!transport_read_frame(rx_buf, &rx_len, PROTO_TIMEOUT_MS)) {
            transport_write(banner, (uint16_t)(sizeof(banner) - 1));
            continue;
        }
        memset(&frame_in, 0, sizeof(frame_in));
        if (!frame_decode(rx_buf, rx_len, &frame_in)) {
            send_simple(MSG_NACK, 0);
            continue;
        }

        if (frame_in.type == MSG_HELLO) {
            send_simple(MSG_ACK, frame_in.seq);
        } else if (frame_in.type == MSG_TEST_META) {
            if (frame_in.len >= 2) {
                test_len = (uint16_t)(frame_in.payload[0] | (frame_in.payload[1] << 8));
                if (test_len > MAX_TEST_VECTOR_BYTES || test_len != shape.input_bytes) {
                    send_simple(MSG_NACK, frame_in.seq);
                } else {
                    send_simple(MSG_ACK, frame_in.seq);
                }
            } else {
                send_simple(MSG_NACK, frame_in.seq);
            }
        } else if (frame_in.type == MSG_TEST_CHUNK) {
            uint16_t logits_len = (shape.output_bytes <= MAX_OUTPUT_BYTES) ? shape.output_bytes : MAX_OUTPUT_BYTES;
            uint32_t t0 = mik32_millis();
            if (!tinyml_infer(frame_in.payload, frame_in.len, &rx_buf[10], &logits_len)) {
                send_simple(MSG_NACK, frame_in.seq);
                continue;
            }
            uint32_t duration_us = (mik32_millis() - t0) * 1000u;

            uint16_t payload_len = (uint16_t)(4u + logits_len);
            rx_buf[0] = FRAME_START;
            rx_buf[1] = MSG_INFER_RESULT;
            rx_buf[2] = (uint8_t)(frame_in.seq & 0xFFu);
            rx_buf[3] = (uint8_t)(frame_in.seq >> 8);
            rx_buf[4] = (uint8_t)(payload_len & 0xFFu);
            rx_buf[5] = (uint8_t)(payload_len >> 8);
            rx_buf[6] = (uint8_t)(duration_us & 0xFFu);
            rx_buf[7] = (uint8_t)((duration_us >> 8) & 0xFFu);
            rx_buf[8] = (uint8_t)((duration_us >> 16) & 0xFFu);
            rx_buf[9] = (uint8_t)((duration_us >> 24) & 0xFFu);
            uint16_t crc = crc16_ccitt(&rx_buf[1], (uint16_t)(5u + payload_len));
            rx_buf[6 + payload_len] = (uint8_t)(crc & 0xFFu);
            rx_buf[7 + payload_len] = (uint8_t)(crc >> 8);
            transport_write(rx_buf, (uint16_t)(8u + payload_len));
            send_simple(MSG_FINISH, frame_in.seq);
        }
    }
}