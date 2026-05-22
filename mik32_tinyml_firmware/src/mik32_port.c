#include "mik32_port.h"

#include "mik32_hal.h"
#include "mik32_hal_pcc.h"
#include "mik32_hal_scr1_timer.h"
#include "mik32_hal_usart.h"

#ifndef MIK32_SERIAL_BAUD
#define MIK32_SERIAL_BAUD 115200u
#endif

#ifndef MIK32_SERIAL_UART
#define MIK32_SERIAL_UART 0
#endif

static USART_HandleTypeDef serial = {0};

void SystemInit(void) {
    HAL_Init();
    __HAL_PCC_GPIO_0_CLK_ENABLE();
    __HAL_PCC_GPIO_1_CLK_ENABLE();
    __HAL_PCC_GPIO_2_CLK_ENABLE();
    __HAL_PCC_GPIO_IRQ_CLK_ENABLE();
}

void mik32_serial_init(uint32_t baud) {
    if (baud == 0) {
        baud = MIK32_SERIAL_BAUD;
    }

    HAL_Time_SCR1TIM_Init();

#if MIK32_SERIAL_UART == 1
    serial.Instance = UART_1;
#else
    serial.Instance = UART_0;
#endif
    serial.transmitting = Enable;
    serial.receiving = Enable;
    serial.frame = Frame_8bit;
    serial.parity_bit = Disable;
    serial.parity_bit_inversion = Disable;
    serial.bit_direction = LSB_First;
    serial.data_inversion = Disable;
    serial.tx_inversion = Disable;
    serial.rx_inversion = Disable;
    serial.swap = Disable;
    serial.lbm = Disable;
    serial.stop_bit = StopBit_1;
    serial.mode = Asynchronous_Mode;
    serial.xck_mode = XCK_Mode0;
    serial.last_byte_clock = Disable;
    serial.overwrite = Enable;
    serial.rts_mode = AlwaysEnable_mode;
    serial.dma_tx_request = Disable;
    serial.dma_rx_request = Disable;
    serial.channel_mode = Duplex_Mode;
    serial.tx_break_mode = Disable;
    serial.baudrate = baud;

    HAL_USART_Init(&serial);
    HAL_USART_ClearFlags(&serial);
}

int mik32_serial_read_byte(uint8_t *out) {
    if (!out || !HAL_USART_RXNE_ReadFlag(&serial)) {
        return 0;
    }

    *out = (uint8_t)HAL_USART_ReadByte(&serial);
    return 1;
}

void mik32_serial_write(const uint8_t *buf, uint16_t len) {
    if (!buf) {
        return;
    }

    for (uint16_t i = 0; i < len; i++) {
        (void)HAL_USART_Transmit(&serial, (char)buf[i], USART_TIMEOUT_DEFAULT);
    }
}

uint32_t mik32_millis(void) {
    return HAL_Time_SCR1TIM_Millis();
}