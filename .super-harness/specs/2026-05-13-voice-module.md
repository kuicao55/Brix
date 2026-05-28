# 语音模块集成设计规格

## 概述

为 Brix 增加语音输入和语音输出，做到"拔插式"集成——完全不影响现有代码架构。

## 核心原则

- **语音是 Transport，不是 Tool**：不做成 Tool 让 Agent 调用，而是独立实时输入通道，与键盘并列
- **Protocol 解耦**：通过 `VoiceRuntime` Protocol 与 Brix 主系统通信
- **Pipecat Pipeline**：作为 voice runtime 编排各 Processor，不是 Orchestrator
- **Hook 统一事件**：语音事件通过 HookRegistry 发送，与其他模块事件同质，FlowLog 统一记录

## 技术栈

| 组件 | 技术选型 | 说明 |
|---|---|---|
| Pipeline 框架 | Pipecat | Processor 链式处理，Frame 类型流转 |
| 唤醒词 | openWakeWord | 检测 "Hey Brix"，通过 Hook 通知主系统 |
| VAD | Silero VAD | 16kHz, 512 samples chunk, 阈值 0.5 |
| STT | faster-whisper | 本地运行，语音结束后整段转录 |
| 语音润色 | Brix LLMClient | 去口头禅、补标点、纠错 |
| TTS | 阿里云 CosyVoice v3 Flash | WebSocket 双工流式合成，24kHz PCM |
| 音频 I/O | PyAudio | 麦克风采集 + 扬声器播放 |

## 目录结构

```
capability/voice/
├── __init__.py
├── protocol.py                  # VoiceRuntime Protocol
├── runtime.py                   # VoiceRuntimeImpl — 生命周期管理 + 状态机
├── pipeline/
│   ├── __init__.py
│   ├── builder.py               # build_voice_pipeline()
│   └── frames.py                # VoiceStateFrame, CleanedTextFrame
├── processors/
│   ├── __init__.py
│   ├── wake_word.py             # WakeWordProcessor (openWakeWord)
│   ├── vad.py                   # VADProcessor (Silero VAD)
│   ├── stt.py                   # STTProcessor (faster-whisper)
│   ├── llm_cleanup.py           # LLMCleanupProcessor
│   └── tts.py                   # TTSProcessor (CosyVoice)
├── transport/
│   ├── __init__.py
│   └── local_audio.py           # LocalAudioTransport (PyAudio)
└── config.py                    # 语音配置
```

## Pipeline 处理器顺序

```
[麦克风] → WakeWord → VAD → STT → LLM Cleanup → [文本桥接到 Brix]
                                                        ↓
[扬声器] ← AudioPlayer ← TTS ←────────────────── [LLM 回复]
```

## Frame 类型流转

| 阶段 | 输入帧 | 输出帧 |
|---|---|---|
| 麦克风 | — | AudioRawFrame(16kHz, mono, int16) |
| WakeWord | AudioRawFrame | AudioRawFrame（唤醒后透传）或丢弃 |
| VAD | AudioRawFrame | AudioRawFrame（有语音时透传） |
| STT | AudioRawFrame | TranscriptionFrame(text) |
| LLM Cleanup | TranscriptionFrame | CleanedTextFrame(text, raw_text) |
| 桥接到 Brix | CleanedTextFrame | — (callback + Hook event) |
| Brix 回复桥入 | — | TextFrame(text) |
| TTS | TextFrame | AudioRawFrame(24kHz, mono, int16) |
| 扬声器 | AudioRawFrame | — |

## Protocol 定义

```python
class VoiceRuntime(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    @property
    def is_running(self) -> bool: ...
    def on_voice_input(self, callback: Callable[[str], None]) -> None: ...
    def on_state_change(self, callback: Callable[[str], None]) -> None: ...
```

## Hook 系统集成

语音模块通过 HookRegistry 与 Brix 主系统统一事件总线，不绕过 Hook：

```python
# VoiceRuntimeImpl 持有 HookRegistry 引用（由 CLI 在创建时传入）
# 语音状态变化 → fire hook
hooks.fire("voice_state", state="wake_detected")
hooks.fire("voice_state", state="speech_start")
hooks.fire("voice_state", state="speech_end")
hooks.fire("voice_state", state="processing")
hooks.fire("voice_state", state="speaking")  # TTS 播放中

# 语音输入完成 → fire hook（包含原始文本和润色文本）
hooks.fire("voice_input", text=cleaned_text, raw=raw_text, cleanup_ms=elapsed)

# TTS 合成完成 → fire hook
hooks.fire("voice_tts", chars=len(text), audio_ms=duration)
```

Hook 的作用：
1. **FlowLog 统一记录**：所有语音事件自动进入 per-turn 流水线日志
2. **可扩展性**：未来可注册自定义 hook 做语音分析、统计等
3. **架构一致性**：与 memory/intent/router/tool_exec 等事件同质

## 集成方式

### Voice → Brix 输入
- LLMCleanupProcessor 产出 CleanedTextFrame 时，通过 callback 调用 `_handle_voice_input(text)`
- 同时通过 `hooks.fire("voice_input", ...)` 记录事件
- CLI 用 `asyncio.wait(FIRST_COMPLETED)` 竞争键盘输入和语音输入队列
- 语音文本走完全相同的 `_process_streaming()` 流程

### Brix 回复 → Voice 输出
- `_process_streaming()` 中，当 voice 激活时，将 text_delta 事件送给 `VoiceRuntime.feed_response_text()`
- TTSProcessor 流式合成后送扬声器播放

### /voice 命令
- 系统命令控制 `VoiceRuntime.start()` / `stop()`

## TTS 流式合成策略

CosyVoice v3 Flash 支持 WebSocket 双工流式合成。TTSProcessor 采用**按句切分、逐句合成、流式播放**策略：

### 文本切分逻辑

```python
import re

def split_sentences(text: str) -> list[str]:
    """按句子边界切分文本。
    规则：句号、问号、感叹号、分号后切分。
    短句（<5字）合并到下一句，避免碎片合成。"""
    raw = re.split(r'([。！？；\n])', text)
    sentences = []
    buf = ""
    for i, part in enumerate(raw):
        buf += part
        if re.match(r'[。！？；\n]', part):
            if len(buf.strip()) >= 5:
                sentences.append(buf.strip())
                buf = ""
            # 短句留在 buf 中，与下一句合并
    if buf.strip():
        if sentences:
            # 最后一段如果太短，合并到上一句
            if len(buf.strip()) < 5:
                sentences[-1] += buf.strip()
            else:
                sentences.append(buf.strip())
        else:
            sentences.append(buf.strip())
    return sentences
```

### 流式调度流程

```
TextFrame(text="你好，我是Brix。今天天气怎么样？")
    │
    ▼ split_sentences
["你好，我是Brix。", "今天天气怎么样？"]
    │
    ▼ 逐句发送到 CosyVoice WebSocket
    ├── 句1 → CosyVoice → [PCM chunk, chunk, ...] → AudioRawFrame → 扬声器
    └── 句2 → CosyVoice → [PCM chunk, chunk, ...] → AudioRawFrame → 扬声器
```

### 关键细节

1. **首包延迟**：每句约 100-300ms 首包（取决于句长），用户感知为"说完就听到回复"
2. **句间缓冲**：见下方"音频缓冲策略"章节
3. **长文本处理**：如果 LLM 回复超过 200 字，按段落边界（\n\n）先分段，每段再分句
4. **中断支持**：用户说话时（VAD 检测到 speech_start），立即停止 TTS 播放（通过 VoiceStateFrame 控制）

### 音频缓冲策略（句间衔接）

CosyVoice 网络延迟抖动可能导致下一句首包不能准时到达，造成音频 underrun（卡顿）。

**方案：TTSProcessor 维护 80ms 预缓冲区**

```python
class TTSProcessor(FrameProcessor):
    """TTS 流式合成 + 预缓冲。"""

    PREFETCH_MS = 80  # 预缓冲毫秒数
    SAMPLE_RATE = 24000
    BYTES_PER_SAMPLE = 2  # int16
    PREFETCH_BYTES = int(SAMPLE_RATE * PREFETCH_MS / 1000) * BYTES_PER_SAMPLE

    def __init__(self, tts_fn):
        self._tts_fn = tts_fn
        self._buffer = bytearray()     # 预缓冲区
        self._prefetch_ready = False   # 是否已积累足够预缓冲

    async def _synthesize_sentence(self, text: str):
        """合成单句，填充预缓冲区后再输出 AudioRawFrame。"""
        async for chunk in self._tts_fn(text):
            self._buffer.extend(chunk)
            if not self._prefetch_ready and len(self._buffer) >= self.PREFETCH_BYTES:
                # 预缓冲就绪，开始输出
                self._prefetch_ready = True
                await self.push_frame(AudioRawFrame(
                    audio=bytes(self._buffer), sample_rate=24000, num_channels=1
                ))
                self._buffer.clear()
            elif self._prefetch_ready:
                # 已就绪，直接输出
                await self.push_frame(AudioRawFrame(
                    audio=chunk, sample_rate=24000, num_channels=1
                ))
        # 句末 flush 残余 buffer
        if self._buffer:
            await self.push_frame(AudioRawFrame(
                audio=bytes(self._buffer), sample_rate=24000, num_channels=1
            ))
            self._buffer.clear()
        self._prefetch_ready = False  # 下一句重新预缓冲
```

**效果**：
- 首句：等积累 80ms 音频后才开始播放，避免刚开始就 underrun
- 句间：下一句的前 80ms 音频已缓冲，即使网络抖动也有余量
- 代价：每句额外 80ms 延迟，用户几乎无感知

## Pipeline 错误处理

Pipecat Pipeline 中任何一个 Processor 抛出未处理异常时，不能导致整个语音 Runtime 僵死。

### 顶层错误边界

VoiceRuntimeImpl 在启动 Pipeline 时包裹顶层 try/except：

```python
class VoiceRuntimeImpl:
    async def _run_pipeline(self):
        """Pipeline 主循环 — 顶层错误边界。"""
        try:
            await self._pipeline.run()
        except Exception as exc:
            logger.error("Voice pipeline crashed: %s", exc, exc_info=True)
            # 通知主系统
            self._hooks.fire("voice_state", state="error", error=str(exc))
            self._state = VoiceConversationState.IDLE
            # 通知 UI
            if self._on_state_change:
                self._on_state_change("error")
            # 清理音频资源
            await self._cleanup_audio()
```

### Processor 级错误隔离

每个 Processor 的 `process_frame` 内部捕获异常，避免单帧错误传播：

```python
async def process_frame(self, frame, direction):
    try:
        # ... 正常逻辑 ...
    except Exception as exc:
        logger.warning("Processor %s error: %s", self.__class__.__name__, exc)
        # 推送错误帧，让下游知道出错了
        await self.push_frame(VoiceStateFrame(
            state="processor_error",
            error=str(exc),
            processor=self.__class__.__name__,
        ), direction)
```

### 恢复策略

| 错误类型 | 恢复行为 |
|---|---|
| STT 推理失败 | 跳过本段语音，回到 SLEEPING，用户可重新说话 |
| LLM Cleanup 失败 | 降级使用原始 STT 文本 |
| TTS 合成失败 | 跳过 TTS，文本回复照常显示，fire `voice_tts_error` hook |
| WebSocket 断连 | 自动重连（3 次），失败则 fire `voice_state=error` |
| PyAudio 设备错误 | 停止 Runtime，fire `voice_state=error`，提示用户检查麦克风 |
| 未知异常 | 捕获 → fire `voice_state=error` → 回到 IDLE |

## 音频重采样

麦克风输入 16kHz，CosyVoice TTS 输出 24kHz。需要在 TTS 输出和扬声器播放之间做重采样。

### 方案：ResampleProcessor

在 TTSProcessor 之后、扬声器 Sink 之前插入 ResampleProcessor：

```
TTSProcessor(24kHz) → ResampleProcessor → AudioPlayerSink(要求统一采样率)
```

```python
class ResampleProcessor(FrameProcessor):
    """音频重采样处理器。使用 scipy.signal.resample_poly 做高质量重采样。"""

    def __init__(self, src_rate: int = 24000, dst_rate: int = 48000):
        self._src_rate = src_rate
        self._dst_rate = dst_rate
        # 计算最简分数: 24000→48000 = 1/2
        from math import gcd
        g = gcd(dst_rate, src_rate)
        self._up = dst_rate // g
        self._down = src_rate // g

    async def process_frame(self, frame, direction):
        if not isinstance(frame, AudioRawFrame):
            await self.push_frame(frame, direction)
            return

        import numpy as np
        from scipy.signal import resample_poly

        samples = np.frombuffer(frame.audio, dtype=np.int16)
        resampled = resample_poly(samples, self._up, self._down)
        resampled_int16 = np.clip(resampled, -32768, 32767).astype(np.int16)

        await self.push_frame(AudioRawFrame(
            audio=resampled_int16.tobytes(),
            sample_rate=self._dst_rate,
            num_channels=frame.num_channels,
        ), direction)
```

### 设计要点

1. **不在 PyAudio 线程中做重采样**：ResampleProcessor 在 Pipecat 的 asyncio event loop 中运行，避免阻塞音频 I/O 线程
2. **scipy.signal.resample_poly** 比简单的线性插值质量高，且支持整数比高效运算
3. **24kHz→48kHz** 是最常见的场景（多数声卡原生 48kHz），也可以配置为其他目标采样率
4. **依赖**：scipy 需要加入 voice optional dependencies

## LLM Cleanup Prompt 模板

LLMCleanupProcessor 使用以下 prompt 调用 Brix 的 LLMClient：

```python
CLEANUP_SYSTEM_PROMPT = """你是语音文本润色器。你的唯一任务是将语音识别（ASR）的原始输出整理为干净的书面文本。

规则：
1. 去除口头禅和填充词：嗯、啊、呃、那个、就是说、然后的话、怎么说呢、对对对、是是是
2. 补全缺失的标点符号（句号、逗号、问号、感叹号）
3. 纠正明显的同音字/语音识别错误（如"在那"→"在哪"，根据上下文判断）
4. 保留原始语义和措辞，不改写内容，不添加信息
5. 如果原文已经是干净文本，直接原样返回
6. 如果原文为空或只有口头禅，返回空字符串

只返回润色后的文本。不要解释、不要加引号、不要加任何前缀。"""

CLEANUP_USER_TEMPLATE = "{raw_text}"
```

### Cleanup 策略细化

| 场景 | 处理方式 |
|---|---|
| 短句（≤5 字） | 跳过 Cleanup，直接透传。短句基本不需要润色，省 200-500ms |
| 纯口头禅（"嗯嗯啊啊"） | Cleanup 返回空字符串，不注入 Brix |
| LLM Cleanup 超时（>2s） | 降级：使用原始 STT 文本，fire `voice_cleanup_timeout` hook |
| Cleanup 结果为空 | 不注入 Brix，fire `voice_cleanup_empty` hook |

### 模型选择

- 默认使用 Brix 配置中的 `intent_model`（通常是轻量模型，延迟低）
- 可通过 config 覆盖：`voice.cleanup.model`
- 未来可替换为本地小模型（如 Qwen2.5-0.5B）进一步降低延迟

## 连续对话模式（P4）

连续对话模式需要独立的对话状态机，管理"听→处理→说→继续听"的循环。

### 状态机定义

```python
from enum import Enum

class VoiceConversationState(Enum):
    """语音对话状态机。"""
    IDLE = "idle"              # 未激活（/voice 未开启）
    SLEEPING = "sleeping"      # 待命：等待唤醒词（非连续模式）或等待语音输入（连续模式）
    LISTENING = "listening"    # 录音中：VAD 检测到语音活动
    PROCESSING = "processing"  # 处理中：STT → Cleanup → Brix LLM
    SPEAKING = "speaking"      # 播放中：TTS 合成并播放
```

### 状态转换

```
                    /voice
    IDLE ──────────────────→ SLEEPING
     ↑                          │
     │ /voice (stop)            │ 唤醒词检测到 (wake_word mode)
     │                          │ VAD 检测到语音 (continuous mode)
     │                          ▼
     │                      LISTENING
     │                          │
     │                          │ 静音 > min_silence_ms (500ms)
     │                          ▼
     │                      PROCESSING
     │                          │
     │                          │ Brix 回复 + TTS 首包就绪
     │                          ▼
     │                      SPEAKING
     │                          │
     │                          │ TTS 播放完成
     │                          ▼
     │          ┌────────── SLEEPING (continuous mode)
     │          │
     │          └────────── IDLE (wake_word mode, 需再次唤醒)
     │
     └──────────────────────────┘  /voice (stop, 从任意状态)
```

### 连续模式 vs 唤醒模式

| 特性 | 唤醒模式（默认） | 连续模式（`--continuous`） |
|---|---|---|
| 进入 LISTENING | 需要说 "Hey Brix" | TTS 播完后自动进入 |
| SPEAKING → ? | → IDLE（需再次唤醒） | → SLEEPING → 自动 LISTENING |
| 超时退出 | 15 秒无语音 → IDLE | 10 秒无语音 → IDLE |
| 适用场景 | 安静环境、偶尔交互 | 连续对话、调试 |

### 超时机制

```python
# 连续模式下的空闲超时
CONTINUOUS_IDLE_TIMEOUT = 10.0  # 秒，SLEEPING 状态下无语音则回到 IDLE
WAKE_IDLE_TIMEOUT = 15.0        # 秒，唤醒模式下唤醒后无语音则回到 IDLE
```

## 三态模型（简化版，P0-P2 使用）

```
IDLE/SLEEP → (唤醒词检测到) → LISTENING → (静音>500ms) → PROCESSING → (TTS完成) → IDLE/SLEEP
```

## VoiceRuntime.stop() 优雅关闭顺序

runtime.py 实现中必须严格遵循此顺序，避免资源泄漏：

1. 设置内部关闭标志（`self._shutdown = True`），阻止新任务进入
2. 中断当前 TTS 播放（通过 VoiceStateFrame 发信号）
3. 停止 VAD 和 WakeWord 的音频流
4. 等待 Pipeline 中所有未完成的帧处理完毕（超时 3s 后强制取消）
5. 关闭 CosyVoice WebSocket 连接
6. 释放 PyAudio 设备（`stream.close()`, `p.terminate()`）
7. `hooks.fire("voice_state", state="idle")`

## 关键设计决策

1. **STT 策略**：语音结束后整段转录（非实时流式），中文效果更好，延迟可接受（200-500ms GPU）
2. **LLM Cleanup**：短句（≤5字）跳过，超时降级使用原始文本
3. **模型懒加载**：只在 `/voice` 首次调用时加载，不拖慢启动
4. **回声消除**：TTS 播放期间禁用 WakeWord 和 VAD（通过 VoiceStateFrame 控制）
5. **连续对话**：P4 阶段支持，独立状态机管理
6. **Hook 统一**：语音事件通过 HookRegistry 发送，FlowLog 统一记录

## 分阶段交付

| 阶段 | 内容 | 验证方式 |
|---|---|---|
| P0 | VAD + STT + LLM Cleanup → 文本输出到终端 | 说话→终端显示润色文本 |
| P1 | + TTS (CosyVoice) → 语音回复 | 说话→语音回答 |
| P2 | + WakeWord + 三态管理 | "Hey Brix" 唤醒 |
| P3 | + /voice 命令 + CLI 集成 | 语音/键盘交替交互 |
| P4 | + 连续对话 + 配置化 | /voice --continuous |

## 坑点与风险

1. **线程模型**：PyAudio callback 在独立线程，需 bridge 到 asyncio event loop
2. **音频对齐**：Silero VAD 要求 512/1024/1536 samples chunk，PyAudio 必须对齐
3. **同步推理**：faster-whisper 和 Silero VAD 需 `asyncio.to_thread()` 隔离
4. **Hook 同步限制**：HookRegistry.fire() 是同步的，语音事件只能同步 fire（不能 await），但 FlowLog 记录本身也是同步操作，无冲突
5. **回声问题**：TTS 播放时扬声器声音被麦克风采集，通过禁用 VAD/STT 解决
6. **模型加载时间**：faster-whisper large-v3 ~3GB/5s，建议默认 small
7. **CosyVoice WebSocket 断连**：自动重连 3 次，失败则 fire voice_state=error
8. **Pipeline 崩溃恢复**：顶层错误边界捕获异常 → fire voice_state=error → 回到 IDLE，不会僵死
9. **音频重采样**：TTS 24kHz → 声卡 48kHz，ResampleProcessor 用 scipy 在 event loop 中处理，不阻塞 I/O 线程
10. **句间 underrun**：TTSProcessor 80ms 预缓冲区吸收网络抖动

## 依赖

```toml
voice = [
    "pipecat-ai>=0.6",
    "faster-whisper>=1.0",
    "openwakeword>=0.6",
    "silero-vad>=5.0",
    "pyaudio>=0.2.14",
    "websockets>=12.0",
    "numpy>=1.24",
    "scipy>=1.11",           # 音频重采样 (resample_poly)
]
```
