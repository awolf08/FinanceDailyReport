from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class Settings:
    timezone: str = "America/Los_Angeles"
    output_dir: Path = Path("reports")
    news_limit: int = 12
    stock_limit: int = 8
    watchlist: tuple[str, ...] = ()
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    report_recipient: str = ""

    @property
    def email_configured(self) -> bool:
        return all([self.smtp_host, self.smtp_user, self.smtp_password, self.report_recipient])

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            timezone=os.getenv("REPORT_TIMEZONE", "America/Los_Angeles"),
            output_dir=Path(os.getenv("REPORT_OUTPUT_DIR", "reports")),
            news_limit=int(os.getenv("REPORT_NEWS_LIMIT", "12")),
            stock_limit=int(os.getenv("REPORT_STOCK_LIMIT", "8")),
            watchlist=parse_csv_symbols(os.getenv("REPORT_WATCHLIST", "")),
            smtp_host=os.getenv("SMTP_HOST", ""),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            report_recipient=os.getenv("REPORT_RECIPIENT", ""),
        )


def parse_csv_symbols(value: str) -> tuple[str, ...]:
    return tuple(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())
