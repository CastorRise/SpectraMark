# 图片隐藏水印工具

本项目提供两种使用方式：

- **双击即用版（推荐）**：一个 HTML 文件，无需安装或启动服务，适合日常批量处理。
- **FastAPI 服务版**：提供网页界面和 HTTP API，适合部署、二次开发和自动化调用。

## 双击即用版

文件：[双击使用-图片隐藏水印.html](../双击使用-图片隐藏水印.html)

### 使用方法

1. 双击 HTML 文件，用 Chrome、Edge、Safari 等现代浏览器打开。
2. 一次选择一张或多张 PNG/JPEG 图片。
3. 输入水印文字，选择强度、输出格式、JPEG 质量和单张像素上限。
4. 点击“开始批量添加水印”，完成后逐张下载或选择“导出全部”。

“导出全部”会直接触发每张图片的下载，不会生成 ZIP。浏览器可能会询问是否允许多文件下载。

### 功能

| 功能 | 说明 |
| --- | --- |
| 批量处理 | 一次选择多张图片，写入同一段隐藏水印 |
| 直接导出 | 支持逐张下载或导出全部，不生成 ZIP |
| 输出格式 | 支持 JPEG 和 PNG，默认 JPEG |
| JPEG 质量 | 80、85、90、95、100，默认 95 |
| 大图支持 | 单张像素上限可设置为 1–60 MP，默认 24 MP |
| 处理强度 | 轻度、均衡、强力三档 |
| 自动校验 | 导出前重新读取最终文件并检测水印 |
| 隐私 | 计算完全在当前浏览器中完成 |

### JPEG 与 PNG

- JPEG 文件通常更小，适合照片和批量导出。页面会重新解码最终 JPEG 并检测水印，验证失败的文件不会显示为成功。
- PNG 不产生 JPEG 压缩损失，适合截图、透明图片或更看重可靠性的场景。
- PNG 保留原图透明通道；JPEG 不支持透明度，透明区域会铺在白色背景上。
- JPEG 校验失败时，可提高质量或水印强度，也可改用 PNG。

### 大图与内存

- 默认单张上限为 24 MP，例如 6000 × 4000。
- 超过用户所设上限的图片会按比例缩小后处理。
- 批量选择时只读取文件信息，正式处理时逐张加载、处理、导出并释放像素数据。
- 60 MP 是可设置的上限，不代表所有设备都能稳定处理；实际能力取决于浏览器和可用内存。

### 单文件版协议

单文件版使用 Haar DWT，并对三个细节频带中的 4×4 块执行 DCT，通过频域系数关系写入比特：

- PNG 主要写入 YCbCr 的 Cr 通道。
- JPEG 主要写入亮度 Y 通道，并使用更适合有损压缩的参数。
- 检测时通过重复投票恢复比特，再以 CRC32 验证完整性。

数据包固定为 275 字节（2200 bit）：

```text
SYNC(8) + MAGIC(4) + VERSION(1) + LENGTH(2) + PAYLOAD_SLOT(256) + CRC32(4)
```

水印最多 64 个 Unicode 码点，UTF-8 编码后最多 256 字节。

> 单文件版使用重复编码、投票和 CRC32；FastAPI 服务版额外使用 Reed–Solomon 纠错，两者协议不兼容。

### 已验证

- 3 张不同尺寸图片批量写入、逐张校验、直接下载：通过。
- 6000 × 4000（24 MP）图片写入和检测：通过。
- “均衡”强度、JPEG 质量 95、最终 JPG 重新解码检测：通过。
- PNG 与 JPEG 三档强度的核心编解码测试：通过。

### 单文件版限制

- 裁剪、旋转、缩放和明显重压缩可能导致水印无法恢复。
- JPEG 可靠性受图片纹理、尺寸、质量和水印强度影响。
- 极小、纯色或低纹理图片可能没有足够容量。
- 使用“导出全部”时，浏览器需要允许多文件下载。

## FastAPI 服务版

服务版位于当前目录，实际结构如下：

```text
hidden-watermark-web/
├── app.py
├── web/
│   ├── api.py
│   ├── config.py
│   ├── routes.py
│   ├── static/
│   └── templates/
├── watermark/
│   ├── block_selector.py
│   ├── decoder.py
│   ├── ecc.py
│   ├── encoder.py
│   ├── metrics.py
│   ├── models.py
│   ├── protocol.py
│   └── transform.py
├── tests/
│   ├── benchmark_algorithms.py
│   ├── robustness_test.py
│   ├── test_api.py
│   ├── test_protocol.py
│   └── test_watermark.py
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

### 环境

- Python 3.9+
- 推荐使用虚拟环境

### 本地启动

```bash
cd hidden-watermark-web
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

### Docker

```bash
docker build -t hidden-watermark-web .
docker run --rm -p 8000:8000 hidden-watermark-web
```

### 算法与协议

服务版使用 Haar DWT + 4×4 DCT，默认通过 Cr 通道中的两组系数关系写入数据。位置选择由图片尺寸确定，重复写入次数取决于强度：

- `low`：1 次
- `balanced`：2 次
- `strong`：3 次

原始协议帧：

```text
MAGIC(8) + VERSION(1) + FLAGS(1) + LENGTH(2) + PAYLOAD_SLOT(256) + CRC32(4)
= 272 bytes
```

272 字节被拆成两个 136 字节数据块，每块增加 32 字节 Reed–Solomon 校验。最终数据包为：

```text
SYNC(16) + RS_CODEWORDS(336) = 352 bytes / 2816 bits
```

### API

#### 服务状态

```http
GET /api/status
```

返回应用版本、协议版本以及字符数、字节数、上传大小、像素数和并发限制。

#### 查询图片容量

```http
POST /api/watermark/capacity
Content-Type: multipart/form-data
```

字段：

- `file`：PNG/JPG/JPEG
- `strength`：`low`、`balanced` 或 `strong`

小图不会先被统一尺寸常量拒绝，而是根据实际协议容量返回 `sufficient`。正方形图片在三档强度下的理论最低边长约为 248、352、432 像素。

#### 添加水印

```http
POST /api/watermark/embed
Content-Type: multipart/form-data
```

字段：

- `file`：PNG/JPG/JPEG
- `message`：1–64 个 Unicode 码点，UTF-8 后最多 256 字节
- `strength`：`low`、`balanced` 或 `strong`
- `output_format`：`png` 或 `jpeg`
- `jpeg_quality`：80、85、90、95 或 100

成功响应示例：

```json
{
  "success": true,
  "message": "内部版权标识",
  "protocol_version": 1,
  "width": 1024,
  "height": 1024,
  "psnr": 43.65,
  "ssim": 0.9936,
  "output_format": "png",
  "strength": "balanced",
  "integrity_verified": true,
  "download_id": "UUID",
  "download_url": "/api/download/UUID",
  "media_type": "image/png"
}
```

服务端会重新读取最终 PNG/JPEG 并检测水印；自校验失败时返回 422，不提供下载文件。

#### 检测水印

```http
POST /api/watermark/detect
Content-Type: multipart/form-data
```

字段：

- `file`：待检测图片

检测到完整水印时：

```json
{
  "found": true,
  "valid": true,
  "damaged": false,
  "message": "内部版权标识",
  "protocol_version": 1,
  "crc_valid": true,
  "ecc_valid": true
}
```

未检测到水印时：

```json
{
  "found": false,
  "valid": false,
  "damaged": false
}
```

#### 下载结果

```http
GET /api/download/{download_id}
```

下载链接仅在当前服务进程中有效，生成文件会在 30 分钟后清理。

### 服务限制与资源保护

- 支持 PNG、JPG、JPEG，不支持动态图。
- 单文件最大 50 MB。
- 单张图片最大 24 MP。
- 水印最多 64 个 Unicode 码点且不超过 256 个 UTF-8 字节。
- 图片解码、DWT/DCT、嵌入、检测和自校验在线程池中运行，不阻塞 FastAPI 事件循环。
- 每个进程默认只允许一个重型图片任务执行，避免多个大图同时造成内存峰值；多 worker 部署时限制按进程计算。

### 临时文件与隐私

- multipart 上传由 Starlette 解析；较大的请求可能由运行环境暂存到系统临时目录。应用读取完毕后会立即关闭上传对象。
- 水印结果写入项目的 `temp/` 目录，以支持后续下载。
- 过期文件在添加、下载时检查，同时由应用生命周期任务每分钟主动清理；启动和关闭时也会清理已过期文件。
- 应用不记录水印文本或图片内容，但反向代理、ASGI 服务器和平台仍可能保留访问日志。
- 公网部署应增加 HTTPS、鉴权、限流和请求体限制。

### 测试

开发依赖单独安装：

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```

当前自动化测试覆盖：

- 首页、状态接口及单一版本来源
- PNG 完整 API 往返与下载
- JPEG 上传、JPEG 输出及最终文件自校验
- 假图片与超长文本拒绝
- 小图按真实容量返回不足
- 下载临时文件过期清理及应用启动/关闭清理
- Unicode 协议往返、同步头、CRC32 和 Reed–Solomon 纠错边界
- PNG 往返、透明通道保留与普通图片误报检查
- JPEG 质量 100/95/90/85/80
- 缩放、亮度、对比度和轻微噪声鲁棒性

当前结果：

```text
35 passed
```

算法组合基准：

```bash
python -m tests.benchmark_algorithms
```

### 已知限制

- 当前方案不支持几何同步；裁剪、旋转和缩放通常会使检测失败。
- JPEG 质量 80 在当前鲁棒性样本中预期失败，质量 85 及以上通过，但不同图片不保证完全相同。
- 24 MP 图片仍可能消耗数百 MB 峰值内存，因此默认串行执行重型任务。

## 工程说明

- 生产依赖位于 `requirements.txt`，测试与 Ruff 位于 `requirements-dev.txt`。
- `pyproject.toml` 统一保存 pytest 和 Ruff 配置。
- GitHub Actions 会在 Python 3.9 与 3.11 上执行 Ruff 和 pytest。
- `.gitignore` 已排除虚拟环境、缓存、临时输出和 `.DS_Store`。
