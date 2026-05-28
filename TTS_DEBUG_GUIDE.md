# TTS 调试指南

我已经添加了详细的日志来诊断 TTS 问题。以下是调试步骤：

## 方法 1: 运行独立测试脚本

```bash
cd ~/Applications/Brix
python test_tts.py
```

这个脚本会：
1. 检查 API Key 是否设置
2. 测试 TTS 客户端创建
3. 测试文本合成
4. 测试音频播放（如果安装了 PyAudio）

## 方法 2: 启用详细日志运行 Brix

```bash
cd ~/Applications/Brix
BRIX_LOG_LEVEL=INFO brix
```

或者启用更详细的 DEBUG 日志：

```bash
BRIX_LOG_LEVEL=DEBUG brix
```

然后使用 `/voice` 命令并说话，你会看到详细的日志输出，包括：

```
12:34:56 [capability.voice.tts.cosyvoice_client] INFO: CosyVoice: Starting synthesis for text: '...' (task_id=...)
12:34:56 [capability.voice.tts.cosyvoice_client] INFO: CosyVoice: Connecting to WebSocket: wss://...
12:34:56 [capability.voice.tts.cosyvoice_client] INFO: CosyVoice: WebSocket connected successfully
12:34:56 [capability.voice.tts.cosyvoice_client] INFO: CosyVoice: Sent run-task message
12:34:56 [capability.voice.tts.cosyvoice_client] INFO: CosyVoice: Received event: task-started
12:34:56 [capability.voice.tts.cosyvoice_client] INFO: CosyVoice: Task started, sending text...
12:34:56 [capability.voice.tts.cosyvoice_client] INFO: CosyVoice: Sent continue-task with text
12:34:56 [capability.voice.tts.cosyvoice_client] INFO: CosyVoice: Sent finish-task, waiting for audio...
12:34:56 [capability.voice.tts.cosyvoice_client] INFO: CosyVoice: Received audio chunk 1, size=XXX bytes
12:34:56 [capability.voice.tts.cosyvoice_client] INFO: CosyVoice: Task finished, total audio chunks=XX
12:34:56 [capability.voice.runtime] INFO: TTS: Success - backend=pyaudio, chunks=XX, bytes=XXXX
```

## 可能的问题和解决方案

### 问题 1: API Key 无效
**日志显示:**
```
CosyVoice task failed before streaming: Invalid API key
```

**解决方案:**
1. 检查 `.env` 文件中的 `ALI_API_KEY` 是否正确
2. 确认 API Key 是否过期
3. 在阿里云控制台重新生成 API Key

### 问题 2: WebSocket 连接失败
**日志显示:**
```
CosyVoice error: [Errno -2] Name or service not known
```

**解决方案:**
1. 检查网络连接
2. 确认可以访问 `dashscope.aliyuncs.com`
3. 检查防火墙设置

### 问题 3: 音频播放失败
**日志显示:**
```
TTS: PyAudio not available, using afplay fallback
```

**解决方案:**
1. 安装 PyAudio: `pip install pyaudio`
2. 或者使用系统播放器（macOS 自带 afplay）

### 问题 4: 音频 chunks 为 0
**日志显示:**
```
TTS produced no audio: '...'
```

**解决方案:**
1. 检查文本是否包含特殊字符
2. 尝试更简单的文本
3. 检查 API 配额是否用尽

## 日志输出位置

所有日志都会输出到终端（stderr）。如果你想保存日志到文件：

```bash
BRIX_LOG_LEVEL=INFO brix 2>&1 | tee brix_tts_debug.log
```

## 快速检查清单

- [ ] `ALI_API_KEY` 已设置且有效
- [ ] 网络可以访问 `dashscope.aliyuncs.com`
- [ ] PyAudio 已安装（或使用 afplay 兜底）
- [ ] 运行 `python test_tts.py` 通过所有测试
- [ ] 使用 `BRIX_LOG_LEVEL=INFO` 查看详细日志

## 需要帮助？

如果问题仍然存在，请提供：
1. `python test_tts.py` 的完整输出
2. `BRIX_LOG_LEVEL=INFO brix` 运行时的完整日志
3. 你的操作系统和 Python 版本
