from typing import List, Dict, Any, Optional
import os

class FileContextManager:
    def __init__(self, default_role: str = "user", chunk_size: int = 2000):
        """
        Initialize the FileContextManager with optional default role and chunk size.

        :param default_role: Role to assign to parsed messages ('user', 'system', etc.)
        :param chunk_size: Max characters per message chunk (used for .txt or .pdf)
        """
        self.default_role = default_role
        self.chunk_size = chunk_size

    def load_files(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Load multiple files and return combined context messages.
        
        :param file_paths: List of file paths to load
        :return: List of message dictionaries
        """
        all_messages = []
        for path in file_paths:
            try:
                messages = self.load_file(path)
                all_messages.extend(messages)
            except Exception as e:
                # Add error message as context
                error_msg = f"Failed to load file {path}: {str(e)}"
                all_messages.append({"role": "system", "content": error_msg})
        
        return all_messages

    def load_file(self, path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

        if path.endswith(".txt"):
            return self._parse_txt(path)
        elif path.endswith(".csv"):
            return self._parse_csv(path)
        elif path.endswith(".pdf"):
            return self._extract_pdf_text(path)
        elif path.endswith(".py"):
            return self._parse_python_file(path)
        elif path.endswith((".md", ".markdown")):
            return self._parse_markdown(path)
        elif path.endswith((".json")):
            return self._parse_json(path)
        else:
            raise ValueError(f"Unsupported file format: {os.path.splitext(path)[1]}")

    def _parse_txt(self, path: str) -> List[Dict[str, Any]]:
        with open(path, encoding="utf-8") as f:
            content = f.read()

        # Optional chunking logic
        chunks = [content[i:i + self.chunk_size] for i in range(0, len(content), self.chunk_size)]
        return [{"role": self.default_role, "content": f"File: {path}\n\n{chunk.strip()}"} for chunk in chunks]

    def _parse_csv(self, path: str) -> List[Dict[str, Any]]:
        import csv
        messages = []
        with open(path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            content_parts = [f"File: {path} (CSV Data)\n"]
            for i, row in enumerate(reader):
                row_content = f"Row {i+1}: " + ", ".join([f"{k}: {v}" for k, v in row.items()])
                content_parts.append(row_content)
            
            full_content = "\n".join(content_parts)
            chunks = [full_content[i:i + self.chunk_size] for i in range(0, len(full_content), self.chunk_size)]
            messages = [{"role": self.default_role, "content": chunk.strip()} for chunk in chunks]
        return messages

    def _extract_pdf_text(self, path: str) -> List[Dict[str, Any]]:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("PyMuPDF is required for PDF processing. Install with: pip install PyMuPDF")
        
        messages = []
        doc = fitz.open(path)
        for i, page in enumerate(doc):
            text = page.get_text().strip()
            if text:
                chunks = [text[j:j + self.chunk_size] for j in range(0, len(text), self.chunk_size)]
                for k, chunk in enumerate(chunks):
                    messages.append({
                        "role": self.default_role,
                        "content": f"File: {path} - Page {i+1}, Part {k+1}:\n{chunk.strip()}"
                    })
        doc.close()
        return messages

    def _parse_python_file(self, path: str) -> List[Dict[str, Any]]:
        with open(path, encoding="utf-8") as f:
            code = f.read()
        return [{
            "role": self.default_role,
            "content": f"File: {path} (Python Code)\n\n```python\n{code}\n```"
        }]

    def _parse_markdown(self, path: str) -> List[Dict[str, Any]]:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        
        chunks = [content[i:i + self.chunk_size] for i in range(0, len(content), self.chunk_size)]
        return [{"role": self.default_role, "content": f"File: {path} (Markdown)\n\n{chunk.strip()}"} for chunk in chunks]

    def _parse_json(self, path: str) -> List[Dict[str, Any]]:
        import json
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        
        content = f"File: {path} (JSON Data)\n\n```json\n{json.dumps(data, indent=2)}\n```"
        chunks = [content[i:i + self.chunk_size] for i in range(0, len(content), self.chunk_size)]
        return [{"role": self.default_role, "content": chunk.strip()} for chunk in chunks]

    def get_supported_extensions(self) -> List[str]:
        """Return list of supported file extensions."""
        return [".txt", ".csv", ".pdf", ".py", ".md", ".markdown", ".json"]