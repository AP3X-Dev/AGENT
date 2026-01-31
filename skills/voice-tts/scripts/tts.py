#!/usr/bin/env python3
"""
Text-to-Speech Script for AG3NT.

Provides TTS functionality using pyttsx3 (cross-platform).

Usage:
    python tts.py speak "Text to speak"
    python tts.py voices

Requires: pip install pyttsx3
"""

import argparse
import json
import sys
from typing import Any

# Try to import pyttsx3
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False


def get_engine():
    """Get the TTS engine, or None if not available."""
    if not HAS_PYTTSX3:
        return None
    try:
        return pyttsx3.init()
    except Exception:
        return None


def speak_text(text: str, voice_id: str | None = None) -> dict[str, Any]:
    """Speak text using TTS."""
    engine = get_engine()
    
    if engine is None:
        return {
            "success": False,
            "error": "TTS not available",
            "suggestion": "Install pyttsx3: pip install pyttsx3",
        }
    
    try:
        # Set voice if specified
        if voice_id:
            engine.setProperty("voice", voice_id)
        
        # Speak the text
        engine.say(text)
        engine.runAndWait()
        
        return {
            "success": True,
            "message": f"Spoke: {text[:50]}{'...' if len(text) > 50 else ''}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_voices() -> dict[str, Any]:
    """List available TTS voices."""
    engine = get_engine()
    
    if engine is None:
        return {
            "success": False,
            "error": "TTS not available",
            "suggestion": "Install pyttsx3: pip install pyttsx3",
        }
    
    try:
        voices = engine.getProperty("voices")
        voice_list = []
        
        for voice in voices:
            voice_list.append({
                "id": voice.id,
                "name": voice.name,
                "languages": getattr(voice, "languages", []),
                "gender": getattr(voice, "gender", None),
            })
        
        return {
            "success": True,
            "count": len(voice_list),
            "voices": voice_list,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def format_result(result: dict[str, Any]) -> str:
    """Format result for human-readable output."""
    if not result.get("success"):
        msg = f"❌ Error: {result.get('error', 'Unknown error')}"
        if result.get("suggestion"):
            msg += f"\n   💡 {result['suggestion']}"
        return msg
    
    if "voices" in result:
        lines = [f"🔊 Available Voices ({result['count']})"]
        lines.append("=" * 40)
        for voice in result["voices"]:
            lines.append(f"  🎤 {voice['name']}")
            lines.append(f"     ID: {voice['id']}")
        return "\n".join(lines)
    
    return f"✅ {result.get('message', 'Operation completed')}"


def main():
    parser = argparse.ArgumentParser(description="Text-to-Speech for AG3NT")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Speak command
    speak_parser = subparsers.add_parser("speak", help="Speak text")
    speak_parser.add_argument("text", help="Text to speak")
    speak_parser.add_argument("--voice", help="Voice ID to use")
    speak_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # Voices command
    voices_parser = subparsers.add_parser("voices", help="List available voices")
    voices_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Execute command
    if args.command == "speak":
        result = speak_text(args.text, args.voice)
    elif args.command == "voices":
        result = list_voices()
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)
    
    # Output
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))
    
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()

