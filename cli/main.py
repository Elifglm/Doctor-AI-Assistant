"""Poliklinik ASR Pipeline - Komut satiri arayuzu."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

console = Console()


def setup_logging(verbose: bool) -> None:
    """Loglama yapilandirmasi."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def create_parser() -> argparse.ArgumentParser:
    """CLI arguman parser olustur."""
    parser = argparse.ArgumentParser(
        description="Poliklinik ASR Pipeline - Otomatik Konusma Tanima",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ornekler:\n"
            "  python -m cli.main ses_dosyasi.wav\n"
            "  python -m cli.main ses_dosyasi.wav --no-denoise\n"
            "  python -m cli.main ses_dosyasi.wav --compute-type int8 --batch-size 8\n"
            "  python -m cli.main ses_dosyasi.wav --min-speakers 2 --max-speakers 3\n"
            "  python -m cli.main ses_dosyasi.wav --output-dir ./sonuclar --verbose\n"
        ),
    )

    parser.add_argument("audio", help="Ses dosyasi yolu (.wav, .mp3, .flac, .m4a, .ogg)")
    parser.add_argument(
        "--no-denoise",
        action="store_true",
        help="Gurultu bastirmayi atla (DeepFilterNet3)",
    )
    parser.add_argument(
        "--compute-type",
        default="float16",
        choices=["float16", "int8"],
        help="Whisper hesaplama tipi (varsayilan: float16)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Whisper batch boyutu (varsayilan: 16)",
    )
    parser.add_argument(
        "--min-speakers",
        type=int,
        default=2,
        help="Minimum konusmaci sayisi (varsayilan: 2)",
    )
    parser.add_argument(
        "--max-speakers",
        type=int,
        default=4,
        help="Maksimum konusmaci sayisi (varsayilan: 4)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Cikti dizini (varsayilan: output/)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Ayrintili log ciktisi",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI giris noktasi."""
    parser = create_parser()
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    console.print(
        Panel.fit(
            "[bold blue]Poliklinik ASR Pipeline[/bold blue]\n"
            "Otomatik Konusma Tanima Sistemi",
            border_style="blue",
        )
    )

    # Dosya kontrolu
    audio_path = Path(args.audio)
    if not audio_path.exists():
        console.print(f"[red]Hata: Dosya bulunamadi: {args.audio}[/red]")
        return 1

    # Ayarlari yapilandir
    from config.settings import AppSettings

    settings = AppSettings()
    settings.deepfilter.enabled = not args.no_denoise
    settings.whisper.compute_type = args.compute_type
    settings.whisper.batch_size = args.batch_size
    settings.diarization.min_speakers = args.min_speakers
    settings.diarization.max_speakers = args.max_speakers
    settings.output.output_dir = args.output_dir

    # Pipeline olustur ve calistir
    from src.pipeline import ASRPipeline

    def progress_callback(stage: str, message: str):
        console.print(f"  [cyan][{stage}][/cyan] {message}")

    pipeline = ASRPipeline(settings)

    console.print(f"\n[bold]Dosya:[/bold] {audio_path.name}")
    console.print(f"[bold]Gurultu bastirma:[/bold] {'Acik' if not args.no_denoise else 'Kapali'}")
    console.print(f"[bold]Hesaplama tipi:[/bold] {args.compute_type}")
    console.print(f"[bold]Batch boyutu:[/bold] {args.batch_size}")
    console.print(f"[bold]Konusmaci araligi:[/bold] {args.min_speakers}-{args.max_speakers}")
    console.print()

    try:
        with console.status("[bold green]Islem basliyor...", spinner="dots"):
            result = pipeline.process(str(audio_path), progress_callback=progress_callback)

        # Sonuclari goster
        console.print("\n[bold green]Islem tamamlandi![/bold green]\n")

        meta = result.get("metadata", {})
        processing = meta.get("processing", {})

        console.print(Panel(
            f"[bold]Sure:[/bold] {meta.get('audio_duration_seconds', 0):.1f} saniye\n"
            f"[bold]Konusmaci sayisi:[/bold] {meta.get('num_speakers', 0)}\n"
            f"[bold]Segment sayisi:[/bold] {len(result.get('segments', []))}\n"
            f"[bold]Toplam islem suresi:[/bold] {processing.get('total', 0):.1f} saniye",
            title="Sonuc Ozeti",
            border_style="green",
        ))

        # Transkript goster
        console.print("\n[bold]Transkript:[/bold]")
        console.print(result.get("full_text", ""))

        # Kaydedilen dosyalar
        saved = result.get("saved_files", {})
        if saved:
            console.print("\n[bold]Kaydedilen dosyalar:[/bold]")
            for fmt, path in saved.items():
                console.print(f"  {fmt.upper()}: {path}")

        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Islem iptal edildi.[/yellow]")
        return 130
    except Exception as e:
        console.print(f"\n[red]Hata: {e}[/red]")
        if args.verbose:
            console.print_exception()
        return 1


if __name__ == "__main__":
    sys.exit(main())
