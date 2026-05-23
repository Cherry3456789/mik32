# MIK32 TinyML Stand

Проект запускает TinyML-модель на плате MIK32/ELBEAR ACE-UNO и прогоняет датасет через реальное устройство. Пользователь передаёт `.tflite` модель и `.npz` датасет, утилита встраивает модель в прошивку, собирает firmware через PlatformIO, прошивает плату, отправляет тестовые векторы по UART и сохраняет метрики.

## Что делает проект

Полный pipeline:

1. Принимает модель `model.tflite`.
2. Конвертирует модель в C-массив `model_data[]`.
3. Встраивает модель в прошивку MIK32.
4. Собирает firmware через PlatformIO.
5. Прошивает плату через `elbear_uploader.exe` или альтернативный upload command.
6. Преобразует датасет `.npz`/`.csv` в бинарный тестовый файл `.mktest`.
7. Отправляет тесты на плату по serial.
8. На плате запускается TensorFlow Lite Micro.
9. С ПК собираются ответы модели, время инференса и итоговые метрики.
10. Результаты сохраняются в `runs/<run_id>/`.

## Структура проекта

```text
.
|-- README.md
|-- tools/
|   |-- patch_tflm.py                   # патчи совместимости TFLM под MIK32/RISC-V
|   |-- runner/
|   |   |-- __main__.py                 # основной CLI: build/flash/probe/run-tests/run-pipeline
|   |   |-- mik32_upload.py             # загрузка firmware на плату
|   |   `-- openocd/
|   |       `-- sipeed-rv-debugger.cfg
|   `-- testgen/
|       `-- __main__.py                 # генерация .mktest из .npz/.csv/случайных данных
`-- mik32_tinyml_firmware/
    |-- platformio.ini                  # конфигурация PlatformIO
    |-- include/
    |   |-- protocol.h
    |   |-- tinyml_runtime.h
    |   `-- transport_serial.h
    |-- model/
    |   |-- model_data.h
    |   `-- model_data.c                # генерируется/обновляется из .tflite
    |-- src/
    |   |-- main.c                      # протокол обмена с ПК
    |   |-- mik32_port.c                # UART, millis, SystemInit для MIK32
    |   |-- protocol.c                  # frame encode/decode + CRC16
    |   |-- tflm_runtime.cc             # TensorFlow Lite Micro runtime
    |   |-- tflm_error_reporter_shim.cc # shim для ErrorReporter
    |   |-- tinyml_runtime.c            # stub guard
    |   `-- transport_serial.c
    `-- lib/
        |-- tflite-micro/               # локальная внешняя зависимость, в git не коммитится
        `-- flatbuffers/                # локальная внешняя зависимость, в git не коммитится
```

## Аппаратная часть

Целевая плата:

```text
ELBEAR ACE-UNO DEV KIT Flash 32MB
MCU: MIK32V2
RAM: 16 KB
External Flash: 32 MB
Serial port example: COM9
```

Для загрузки через Arduino-compatible bootloader используется:

```text
elbear_uploader.exe
```

Пример команды, которую Arduino IDE использовала для этой платы:

```powershell
"C:\Users\User\AppData\Local\Arduino15\packages\Elron\tools\elbear_uploader\0.2.2\elbear_uploader.exe" `
  "firmware.hex" `
  --com=COM9 `
  --baudrate=230400
```

## Подготовка окружения

### 1. Python

Рекомендуется Python 3.10+.

Проверка:

```powershell
python --version
```

Создание виртуального окружения:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Установка Python-зависимостей:

```powershell
python -m pip install --upgrade pip
python -m pip install platformio pyserial numpy
```

`platformio` нужен для сборки прошивки, `pyserial` для обмена по COM-порту, `numpy` для чтения `.npz`/`.npy`.

### 2. PlatformIO

Проверка:

```powershell
python -m platformio --version
```

Сборка вызывается из корня проекта:

```powershell
python -m tools.runner build
```

### 3. Установка внешних C/C++ библиотек

Большие внешние библиотеки не коммитятся в git. Их нужно установить локально в `mik32_tinyml_firmware/lib/`.

TensorFlow Lite Micro:

```powershell
git clone https://github.com/tensorflow/tflite-micro.git mik32_tinyml_firmware\lib\tflite-micro
```

FlatBuffers:

```powershell
git clone https://github.com/google/flatbuffers.git mik32_tinyml_firmware\lib\flatbuffers
cd mik32_tinyml_firmware\lib\flatbuffers
git checkout v25.9.23
cd ..\..\..
```

Gemmlowp, если файла `fixedpoint.h` нет:

```powershell
git clone https://github.com/google/gemmlowp.git mik32_tinyml_firmware\lib\tflite-micro\third_party\gemmlowp
```

Проверка:

```powershell
Test-Path mik32_tinyml_firmware\lib\tflite-micro\tensorflow\lite\micro\micro_interpreter.h
Test-Path mik32_tinyml_firmware\lib\flatbuffers\include\flatbuffers\flatbuffers.h
Test-Path mik32_tinyml_firmware\lib\tflite-micro\third_party\gemmlowp\fixedpoint\fixedpoint.h
```

Все три команды должны вернуть `True`.

### 4. Патчи TFLM

Перед сборкой PlatformIO автоматически запускает:

```ini
extra_scripts =
  pre:../tools/patch_tflm.py
```

Скрипт `tools/patch_tflm.py` делает два действия:

- патчит `cppmath.h`, чтобы RISC-V toolchain корректно находил `round`/`expm1`;
- создаёт no-op stub `ruy/profiler/instrumentation.h`, который нужен части TFLM kernels.

Запустить вручную можно так:

```powershell
python tools\patch_tflm.py
```

## Конфигурация прошивки

Основной файл:

```text
mik32_tinyml_firmware/platformio.ini
```

Ключевые настройки:

```ini
board_build.ldscript = spifi
board_upload.maximum_size = 33554432

build_flags =
  -DTINYML_USE_TFLM=1
  -DTINYML_TENSOR_ARENA_BYTES=8192
  -DMAX_TEST_VECTOR_BYTES=1024
  -DMAX_OUTPUT_BYTES=256
  -DMAX_BATCH=64
  -DPROTO_TIMEOUT_MS=2000

upload_protocol = custom
upload_command = python ../tools/runner/mik32_upload.py "$SOURCE"
```

Значение `board_upload.maximum_size = 33554432` важно для ELBEAR ACE-UNO Flash 32MB. Без него PlatformIO считает, что доступно только 8 KB flash.

`TINYML_TENSOR_ARENA_BYTES` задаёт размер tensor arena для TFLM. Сейчас стоит `8192`. Если `tinyml_init()` не проходит, возможно модели нужно больше arena, но у платы всего 16 KB RAM, поэтому увеличивать это значение нужно осторожно.

## Поддерживаемые операции модели

В `mik32_tinyml_firmware/src/tflm_runtime.cc` сейчас подключён маленький resolver:

```cpp
resolver->AddFullyConnected()
resolver->AddReshape()
resolver->AddSoftmax()
resolver->AddQuantize()
resolver->AddDequantize()
```

Это значит, что модель `.tflite` должна использовать только эти операции. Если TFLM вернёт ошибку на этапе `AllocateTensors()` или `Invoke()`, нужно проверить список operators модели и добавить недостающие операции в `add_model_ops()`.

Пример:

```cpp
resolver->AddConv2D();
resolver->AddAveragePool2D();
```

После добавления новой операции может понадобиться добавить соответствующий `.cc` файл в:

```text
mik32_tinyml_firmware/lib/tflite-micro/library.json
```

## Входные файлы

### Модель

Формат:

```text
model.tflite
```

Требования:

- файл должен быть настоящим TFLite FlatBuffer;
- модель должна помещаться во flash;
- входной tensor модели должен совпадать с форматом датасета;
- выходной tensor должен помещаться в `MAX_OUTPUT_BYTES`;
- операции модели должны быть добавлены в TFLM resolver.

Проверка файла:

```powershell
python -m tools.runner model-info `
  --model "C:\path\to\model.tflite"
```

### Датасет

Основной формат:

```text
dataset.npz
```

Поддерживаемые ключи входных данных:

```text
x, X, features, vectors, images, data, inputs, texts, text, arr_0
```

Поддерживаемые ключи labels:

```text
y, Y, labels, label, target, targets, arr_1
```

Можно указать ключи вручную:

```powershell
--npz-key input
--npz-label-key label
```

Для реального TFLM-прогона датасет должен содержать числовой tensor, например:

```text
input: float32, shape = (N, 4)
label: int64, shape = (N,)
```

Строковые датасеты технически можно преобразовать в diagnostic bytes, но это не настоящий NLP pipeline. Для реальной text-модели нужен тот же tokenizer/preprocessing, с которым модель обучалась.

Проверка модели и датасета:

```powershell
python -m tools.runner model-info `
  --model "C:\path\to\model.tflite" `
  --dataset "C:\path\to\dataset.npz"
```

Пример вывода:

```json
{
  "model": {
    "path": "model.tflite",
    "size_bytes": 1234,
    "is_tflite": true
  },
  "dataset": {
    "kind": "npz",
    "keys": ["input", "label", "logits"],
    "input_key": "input",
    "label_key": "label",
    "input_shape": [120, 4],
    "input_dtype": "float32",
    "sample_input_bytes": 16,
    "label_shape": [120],
    "label_dtype": "int64",
    "output_shape": [120, 3],
    "output_dtype": "float32"
  }
}
```

## Промежуточный формат `.mktest`

`tools.testgen` преобразует датасет в бинарный файл:

```text
tests.mktest
```

Формат файла:

```text
offset  size  meaning
0       4     magic: "MKT1"
4       2     version, little-endian
6       4     count, little-endian
10      2     vec_len, little-endian
12      ...   count vectors, each vec_len bytes
```

Если входной tensor `float32` формы `(N, 4)`, один sample занимает:

```text
4 values * 4 bytes = 16 bytes
```

Значит `vec_len = 16`.

Генерация из `.npz`:

```powershell
python -m tools.testgen generate `
  --input dataset.npz `
  --output tests.mktest `
  --count 32
```

Генерация с явным ключом:

```powershell
python -m tools.testgen generate `
  --input dataset.npz `
  --output tests.mktest `
  --count 32 `
  --npz-key input `
  --npz-label-key label
```

Генерация случайных тестов:

```powershell
python -m tools.testgen generate `
  --output tests.mktest `
  --count 32 `
  --vec-len 784 `
  --seed 42
```

Проверка `.mktest`:

```powershell
python -m tools.testgen inspect --input tests.mktest
```

Рядом создаётся:

```text
tests.manifest.json
```

В нём хранятся `count`, `vec_len`, тип входа, shape и labels, если они есть.

## Serial protocol между ПК и платой

Обмен идёт кадрами с CRC16.

Формат frame:

```text
byte 0      start = 0xAA
byte 1      message type
byte 2..3   seq, little-endian
byte 4..5   payload length, little-endian
payload     payload bytes
last 2      CRC16-CCITT over type + seq + len + payload
```

Типы сообщений:

```text
0x01 MSG_HELLO
0x02 MSG_TEST_META
0x03 MSG_TEST_CHUNK
0x04 MSG_INFER_RESULT
0x05 MSG_ACK
0x06 MSG_NACK
0x07 MSG_FINISH
```

Последовательность одного теста:

1. ПК отправляет `MSG_HELLO`.
2. Плата отвечает `MSG_ACK`.
3. ПК отправляет `MSG_TEST_META`, payload содержит длину входного tensor в байтах.
4. Плата проверяет длину против `shape.input_bytes`.
5. Плата отвечает `MSG_ACK` или `MSG_NACK`.
6. ПК отправляет `MSG_TEST_CHUNK`, payload содержит raw bytes sample.
7. Плата вызывает `tinyml_infer()`.
8. Плата отправляет `MSG_INFER_RESULT`.
9. Плата отправляет `MSG_FINISH`.

Payload `MSG_INFER_RESULT`:

```text
offset  size  meaning
0       4     duration_us, uint32 little-endian
4       ...   raw output tensor bytes
```

На ПК output tensor декодируется через `--output-dtype`:

```text
uint8
int8
float32
int32
auto
```

В `run-pipeline` режим `auto` пытается взять dtype из ключа `logits` в `.npz`, если он есть. Иначе используется `uint8`.

## Основные команды

Все команды выполняются из корня проекта.

### Сборка прошивки

```powershell
python -m tools.runner build
```

Успешная сборка выглядит так:

```text
RAM:   [========  ]  76.0% (used 12444 bytes from 16384 bytes)
Flash: [          ]   0.3% (used 111768 bytes from 33554432 bytes)
[SUCCESS]
```

### Прошивка платы

Для ELBEAR uploader:

```powershell
$env:MIK32_UPLOAD_PORT="COM9"
$env:MIK32_UPLOAD_BAUD="230400"
python -m tools.runner flash
```

Если `elbear_uploader.exe` не найден автоматически:

```powershell
$env:ELBEAR_UPLOADER="C:\Users\User\AppData\Local\Arduino15\packages\Elron\tools\elbear_uploader\0.2.2\elbear_uploader.exe"
```

Если нужен полностью свой upload command:

```powershell
$env:MIK32_UPLOAD_CMD='my_uploader --port COM9 --file {firmware}'
python -m tools.runner flash
```

`{firmware}` будет заменён на путь к `.hex`/firmware, который передаёт PlatformIO.

### Проверка связи

```powershell
python -m tools.runner probe --port COM9 --baud 115200 --seconds 5
```

Нормальный результат:

```text
listening on COM9 at 115200 for 5.0s
raw text: 'MIK32_TINYML_READY\r\n...'
hello: ok
```

Если есть `MIK32_TINYML_READY`, но `hello: no ack`, значит TX платы работает, но плата не отвечает на входящие frame. Возможные причины:

- прошита старая версия firmware;
- не хватает RAM/переполнение стека;
- firmware зависла после баннера;
- выбран не тот UART;
- ПК открыл не тот COM-порт;
- serial monitor или Arduino IDE удерживает порт.

### Ручной прогон готовых `.mktest`

```powershell
python -m tools.runner run-tests `
  --port COM9 `
  --tests tests.mktest `
  --out results.json `
  --output-dtype float32
```

Результат:

```text
results.json
```

### Полный pipeline

```powershell
$env:MIK32_UPLOAD_PORT="COM9"
$env:MIK32_UPLOAD_BAUD="230400"

python -m tools.runner run-pipeline `
  --model "C:\path\to\model.tflite" `
  --dataset "C:\path\to\dataset.npz" `
  --port COM9 `
  --count 32
```

С явными ключами датасета:

```powershell
python -m tools.runner run-pipeline `
  --model "C:\path\to\model.tflite" `
  --dataset "C:\path\to\dataset.npz" `
  --port COM9 `
  --count 32 `
  --npz-key input `
  --npz-label-key label `
  --output-dtype float32
```

Если нужно указать размер sample вручную:

```powershell
--vec-len 16
```

Обычно `--vec-len` можно не указывать: для числового `.npz` утилита вычисляет размер одного sample как:

```text
number_of_elements_per_sample * dtype.itemsize
```

## Выходные файлы

После `run-pipeline` создаётся папка:

```text
runs/<run_id>/
```

Пример:

```text
runs/
└── 4fe6df60-1827-49ac-ae46-812afbf34cc9/
    ├── model.tflite
    ├── dataset.npz
    ├── tests.mktest
    ├── tests.manifest.json
    ├── results.json
    ├── predictions.csv
    └── report.json
```

### `results.json`

Сырые результаты с платы:

```json
{
  "count": 32,
  "vec_len": 16,
  "output_dtype": "float32",
  "results": [
    {
      "id": 0,
      "prediction": 1,
      "logits": [0.1, 0.7, 0.2],
      "duration_us": 1000
    }
  ]
}
```

### `predictions.csv`

Таблица для просмотра:

```text
id,prediction,label,correct,duration_us,logits
```

### `report.json`

Итоговая сводка:

```json
{
  "count": 32,
  "vec_len": 16,
  "latency_us": {
    "min": 0,
    "max": 1000,
    "avg": 187.5,
    "median": 0
  },
  "accuracy": 0.875,
  "correct": 28,
  "has_labels": true
}
```

`accuracy` считается только если в `.npz` есть числовые labels.

### Метрики памяти

Сейчас память выводит PlatformIO во время build:

```text
RAM:   [========  ]  76.0% (used 12444 bytes from 16384 bytes)
Flash: [          ]   0.3% (used 111768 bytes from 33554432 bytes)
```

Для веб-интеграции backend может:

- парсить stdout команды `run-pipeline`;
- либо отдельно вызывать `python -m tools.runner build` и сохранять строки `RAM:`/`Flash:`;
- либо позже добавить парсер в `tools.runner`, чтобы память попадала прямо в `report.json`.

## Как работает прошивка

### `main.c`

Файл:

```text
mik32_tinyml_firmware/src/main.c
```

Задачи:

- инициализирует transport;
- отправляет баннер `MIK32_TINYML_READY`;
- вызывает `tinyml_init()`;
- принимает frames по UART;
- отвечает на `HELLO`;
- проверяет длину входного tensor;
- запускает `tinyml_infer()`;
- отправляет `duration_us` и raw output tensor.

### `tflm_runtime.cc`

Файл:

```text
mik32_tinyml_firmware/src/tflm_runtime.cc
```

Задачи:

- берёт модель из `model_data[]`;
- создаёт `MicroMutableOpResolver`;
- создаёт `MicroInterpreter`;
- выделяет tensor arena;
- вызывает `AllocateTensors()`;
- запоминает input/output tensor;
- выполняет `interpreter->Invoke()`.

Методы:

```c
bool tinyml_init(tinyml_shape_t *shape);
bool tinyml_infer(const uint8_t *input, uint16_t input_len, uint8_t *output, uint16_t *output_len);
```

`tinyml_init()` возвращает:

- `shape.input_bytes`;
- `shape.output_bytes`.

`tinyml_infer()` принимает raw bytes входного tensor и возвращает raw bytes выходного tensor.

### `mik32_port.c`

Файл:

```text
mik32_tinyml_firmware/src/mik32_port.c
```

Задачи:

- `SystemInit()`;
- включение clock для GPIO;
- настройка USART;
- чтение/запись байтов;
- таймер `mik32_millis()`.

Настройки:

```c
#define MIK32_SERIAL_BAUD 115200u
#define MIK32_SERIAL_UART 0
```

Если нужен другой UART:

```ini
-DMIK32_SERIAL_UART=1
```

## Как интегрировать с веб-интерфейсом

Веб-интерфейс должен быть тонкой оболочкой над CLI. Рекомендуемая архитектура:

```text
Browser
  ↓ HTTP upload
Backend service
  ↓ saves uploaded model/dataset
python -m tools.runner run-pipeline
  ↓
runs/<run_id>/report.json
runs/<run_id>/predictions.csv
runs/<run_id>/results.json
  ↓
Backend returns status and artifacts
```

### API, который удобно сделать на backend

#### `POST /runs`

Вход:

```text
multipart/form-data
- model: .tflite
- dataset: .npz
- board: mik32_elbear_ace_uno
- port: COM9
- count: optional
- npz_key: optional
- npz_label_key: optional
- output_dtype: optional
```

Backend:

1. Создаёт `run_id`.
2. Сохраняет файлы в `runs/<run_id>/uploads/`.
3. Запускает:

```powershell
python -m tools.runner run-pipeline `
  --model "runs\<run_id>\uploads\model.tflite" `
  --dataset "runs\<run_id>\uploads\dataset.npz" `
  --port COM9 `
  --count 32 `
  --run-id "<run_id>"
```

4. Читает `runs/<run_id>/report.json`.
5. Возвращает JSON.

Выход:

```json
{
  "run_id": "uuid",
  "status": "completed",
  "report": {
    "accuracy": 0.875,
    "latency_us": {
      "median": 1000
    }
  },
  "artifacts": {
    "report": "/runs/uuid/report.json",
    "predictions": "/runs/uuid/predictions.csv",
    "results": "/runs/uuid/results.json"
  }
}
```

#### `GET /runs`

Возвращает список папок `runs/<run_id>/` и краткую сводку из `report.json`.

#### `GET /runs/<run_id>`

Возвращает:

- статус;
- `report.json`;
- путь к артефактам.

#### `GET /runs/<run_id>/artifacts/<name>`

Скачивание:

- `report.json`;
- `predictions.csv`;
- `results.json`;
- `tests.manifest.json`.

### Важное для веб-интеграции

Нельзя запускать две прошивки одновременно на один и тот же COM-порт. На backend нужен lock:

```text
one board port = one active run
```

Также перед запуском нужно закрыть:

- Arduino Serial Monitor;
- PlatformIO monitor;
- другие программы, которые держат COM-порт.

## Типовые сценарии

### Проверить только связь с платой

```powershell
python -m tools.runner probe --port COM9
```

### Собрать и прошить текущую модель

```powershell
python -m tools.runner build

$env:MIK32_UPLOAD_PORT="COM9"
$env:MIK32_UPLOAD_BAUD="230400"
python -m tools.runner flash
```

### Прогнать случайные тесты

```powershell
python -m tools.testgen generate `
  --output tests.mktest `
  --count 32 `
  --vec-len 16

python -m tools.runner run-tests `
  --port COM9 `
  --tests tests.mktest `
  --out results.json `
  --output-dtype float32
```

### Полный пользовательский запуск

```powershell
$env:MIK32_UPLOAD_PORT="COM9"
$env:MIK32_UPLOAD_BAUD="230400"

python -m tools.runner run-pipeline `
  --model "C:\Users\Анна\Downloads\model.tflite" `
  --dataset "C:\Users\Анна\Downloads\dataset.npz" `
  --port COM9 `
  --count 32 `
  --npz-key input `
  --npz-label-key label `
  --output-dtype float32
```

## Ограничения текущей версии

- Поддерживаются только операции, добавленные в `add_model_ops()`.
- Препроцессинг на плате минимальный: входной sample отправляется как raw tensor bytes.
- Для текстовых моделей нужен отдельный tokenizer/preprocessing pipeline.
- RAM платы ограничена 16 KB.
- `TINYML_TENSOR_ARENA_BYTES=8192` может быть мало для более сложных моделей.
- `MAX_TEST_VECTOR_BYTES=1024`, входной tensor больше этого размера не принимается.
- `MAX_OUTPUT_BYTES=256`, output tensor больше этого размера будет отклонён/обрезан логикой firmware.
- Метрики памяти пока берутся из stdout PlatformIO, а не из `report.json`.

## Диагностика ошибок

### `No module named platformio`

Установить PlatformIO в тот Python, которым запускается проект:

```powershell
python -m pip install platformio
```

### `No module named serial`

```powershell
python -m pip install pyserial
```

### `No HELLO ack`

Проверить:

```powershell
python -m tools.runner probe --port COM9 --baud 115200 --seconds 5
```

Если нет даже `MIK32_TINYML_READY`:

- не та прошивка;
- не тот COM-порт;
- плата не перезапустилась;
- UART не тот.

Если `MIK32_TINYML_READY` есть, но `hello: no ack`:

- прошивка зависла после старта;
- не хватает RAM;
- прошит старый бинарник;
- COM-порт занят другой программой;
- RX платы не подключён к нужному UART.

### `No ACK for META`

Обычно означает, что размер sample в `.mktest` не совпадает с `shape.input_bytes` модели.

Проверить датасет:

```powershell
python -m tools.runner model-info `
  --model model.tflite `
  --dataset dataset.npz
```

Если input `float32` shape `(N, 4)`, `vec_len` должен быть `16`.

### Ошибка линковки TFLM

Проверить:

- есть ли `mik32_tinyml_firmware/lib/tflite-micro`;
- есть ли `mik32_tinyml_firmware/lib/flatbuffers`;
- есть ли `gemmlowp`;
- запустился ли `tools/patch_tflm.py`;
- не изменился ли список файлов в `library.json`.

### Модель не запускается

Возможные причины:

- в модели есть операция, которой нет в resolver;
- не хватает tensor arena;
- input dtype/shape не совпадает с датасетом;
- output tensor больше `MAX_OUTPUT_BYTES`;
- модель слишком большая или требует слишком много RAM.

## Git и артефакты

В git нужно коммитить:

- исходники `tools/`;
- исходники `mik32_tinyml_firmware/src`;
- заголовки `mik32_tinyml_firmware/include`;
- `platformio.ini`;
- `README.md`;
- `.gitignore`;
- `mik32_tinyml_firmware/lib/tflite-micro/library.json`;

Не нужно коммитить:

- `.pio/`;
- `runs/`;
- `*.tflite`;
- `*.npz`;
- `*.npy`;
- `*.mktest`;
- `__pycache__/`;
- полные исходники `tflite-micro`;
- полные исходники `flatbuffers`.

Причина: TFLM и FlatBuffers очень большие, их лучше устанавливать локально по инструкции.

## Краткая команда для демо

```powershell
python -m pip install platformio pyserial numpy

python tools\patch_tflm.py

$env:MIK32_UPLOAD_PORT="COM9"
$env:MIK32_UPLOAD_BAUD="230400"

python -m tools.runner run-pipeline `
  --model "C:\Users\Анна\Downloads\model.tflite" `
  --dataset "C:\Users\Анна\Downloads\dataset.npz" `
  --port COM9 `
  --count 32 `
  --npz-key input `
  --npz-label-key label `
  --output-dtype float32
```