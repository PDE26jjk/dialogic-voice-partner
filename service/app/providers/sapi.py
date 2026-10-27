"""Windows SAPI provider: uses the voices already installed in the system.

Synthesis shells out to Windows PowerShell because `System.Speech` lives in the
.NET Framework, which pwsh 7 does not ship. Text is passed through a UTF-8 file
so no quoting or injection issues can reach the script.
"""

from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

from . import ModelInfo, ModelParam, Provider, SynthesisResult, VoiceInfo

POWERSHELL = "powershell.exe"
TIMEOUT_SECONDS = 120

_DISCOVER = """
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
foreach ($voice in $synth.GetInstalledVoices()) {
  if ($voice.Enabled) { "$($voice.VoiceInfo.Name)|$($voice.VoiceInfo.Culture.Name)" }
}
"""

_SYNTHESIZE = """
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $synth.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Name -eq '{voice}' }} | Select-Object -First 1
if ($null -eq $voice) {{ Write-Error "voice not found: {voice}"; exit 1 }}
$synth.SelectVoice('{voice}')
$synth.Rate = {rate}
$synth.SetOutputToWaveFile('{output}')
$text = [System.IO.File]::ReadAllText('{input}', [System.Text.Encoding]::UTF8)
$synth.Speak($text)
$synth.Dispose()
"""


class SapiProvider(Provider):
    id = "sapi"
    label = "Windows SAPI (system voices)"
    models = [
        ModelInfo(
            id="system",
            label="System voice",
            params=[
                ModelParam(
                    id="rate",
                    label="Rate",
                    type="number",
                    default=0,
                    minimum=-10,
                    maximum=10,
                    step=1,
                )
            ],
        )
    ]
    _voices: list[VoiceInfo] | None = None

    @property
    def voices(self) -> list[VoiceInfo]:
        if self._voices is None:
            self._voices = self._discover()
        return self._voices

    @staticmethod
    def _discover() -> list[VoiceInfo]:
        try:
            result = subprocess.run(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    _DISCOVER,
                ],
                capture_output=True,
                text=True,
                timeout=20,
                encoding="utf-8",
                errors="ignore",
            )
        except (OSError, subprocess.SubprocessError):
            return []

        voices: list[VoiceInfo] = []
        for line in result.stdout.splitlines():
            name = line.strip()
            if not name or "|" not in name:
                continue
            voice_id, _, culture = name.partition("|")
            label = f"{voice_id} ({culture})" if culture else voice_id
            voices.append(VoiceInfo(id=voice_id.strip(), label=label))
        return voices

    def synthesize(
        self,
        model: str,
        prompt: str,
        params: dict,
        voice: str | None = None,
    ) -> SynthesisResult:
        available = [item.id for item in self.voices]
        if not available:
            raise ValueError("No SAPI voices are installed on this machine.")
        chosen = voice or available[0]
        if chosen not in available:
            raise ValueError(f"Unknown SAPI voice: {chosen}")

        rate = max(-10, min(10, int(params.get("rate", 0) or 0)))

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            text_path = directory / "text.txt"
            output_path = directory / "out.wav"
            text_path.write_text(prompt, encoding="utf-8")

            script = _SYNTHESIZE.format(
                voice=chosen.replace("'", "''"),
                rate=rate,
                output=str(output_path).replace("'", "''"),
                input=str(text_path).replace("'", "''"),
            )
            result = subprocess.run(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                encoding="utf-8",
                errors="ignore",
            )
            if result.returncode != 0 or not output_path.is_file():
                message = (result.stderr or result.stdout or "SAPI synthesis failed").strip()
                raise ValueError(message.splitlines()[-1] if message else "SAPI synthesis failed")

            payload = output_path.read_bytes()
            with wave.open(str(output_path), "rb") as handle:
                duration_ms = int(handle.getnframes() / handle.getframerate() * 1000)

        return SynthesisResult(audio=payload, extension="wav", duration_ms=duration_ms)
