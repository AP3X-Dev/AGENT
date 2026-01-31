---
name: voice-tts
description: Text-to-speech output for voice responses. Uses pyttsx3 for local TTS on supported systems.
version: "1.0.0"
tags:
  - voice
  - audio
  - tts
  - device
triggers:
  - "say something"
  - "speak"
  - "read aloud"
  - "voice output"
entrypoints:
  speak:
    script: scripts/tts.py speak
    description: Speak text using text-to-speech
  list-voices:
    script: scripts/tts.py voices
    description: List available TTS voices
required_permissions:
  - audio_output
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: device-integration
  node_capability: audio_output
---

# Voice TTS Skill

This skill provides text-to-speech functionality using the local system's TTS capabilities.

## When to Use

- User asks to "say" or "speak" something
- User wants information read aloud
- Voice assistant interactions

## Available Commands

### Speak Text
Convert text to speech and play it through the default audio output.

```bash
python scripts/tts.py speak "Hello, I am your assistant."
```

### List Available Voices
Show available TTS voices on the system.

```bash
python scripts/tts.py voices
```

## Dependencies

This skill requires `pyttsx3` for cross-platform TTS:

```bash
pip install pyttsx3
```

## Platform Support

| Platform | TTS Engine | Notes |
|----------|-----------|-------|
| Windows | SAPI5 | ✅ Built-in |
| macOS | NSSpeechSynthesizer | ✅ Built-in |
| Linux | espeak | ⚠️ May require: `sudo apt install espeak` |

## Notes

- Audio output goes to default system speakers
- Voice selection depends on installed system voices
- Speed and volume can be adjusted
- Works offline (no internet required)

