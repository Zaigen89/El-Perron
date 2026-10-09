"""Memoria del bot: conocimiento que tú le das (knowledge/) y lecciones que él aprende (memory/)."""
from __future__ import annotations

from pathlib import Path

MAX_KNOWLEDGE_CHARS = 20_000
MAX_LESSONS_CHARS = 8_000


class Memory:
    def __init__(self, knowledge_dir: str | Path = "knowledge", memory_dir: str | Path = "memory"):
        self.knowledge_dir = Path(knowledge_dir)
        self.memory_dir = Path(memory_dir)
        self.lessons_path = self.memory_dir / "lessons.md"

    def knowledge(self) -> str:
        """Concatena todos los .md de knowledge/ en orden alfabético (por eso los prefijos 01_, 02_...)."""
        if not self.knowledge_dir.exists():
            return ""
        parts = []
        for p in sorted(self.knowledge_dir.glob("*.md")):
            if p.name.startswith("00_"):
                continue  # la plantilla no se envía
            parts.append(f"### {p.stem}\n{p.read_text(encoding='utf-8').strip()}")
        text = "\n\n".join(parts)
        if len(text) > MAX_KNOWLEDGE_CHARS:
            text = text[:MAX_KNOWLEDGE_CHARS] + "\n[... conocimiento truncado ...]"
        return text

    def lessons(self) -> str:
        if not self.lessons_path.exists():
            return ""
        text = self.lessons_path.read_text(encoding="utf-8").strip()
        if len(text) > MAX_LESSONS_CHARS:
            text = text[-MAX_LESSONS_CHARS:]
        return text

    def write_lessons(self, text: str) -> Path:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.lessons_path.write_text(text.strip() + "\n", encoding="utf-8")
        return self.lessons_path
