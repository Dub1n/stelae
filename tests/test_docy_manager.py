import json
from pathlib import Path

from stelae_lib.docy_catalog import DocyCatalog
import scripts.docy_manager_server as docy_server


def test_add_and_render(tmp_path):
    catalog_path = tmp_path / "docy_sources.json"
    catalog_path.write_text('{"sources": []}', encoding="utf-8")
    url_file = tmp_path / ".docy.urls"

    catalog = DocyCatalog.load(catalog_path)
    entry, action = catalog.add_source(url="https://example.com/docs", title="Example Docs")
    assert action == "created"
    assert entry.id.startswith("example-docs")

    catalog.save()
    lines = catalog.render_urls(url_file)
    assert "https://example.com/docs" in lines[-1]
    assert url_file.exists()

    catalog = DocyCatalog.load(catalog_path)
    removed = catalog.remove_source(source_id=entry.id)
    assert removed.id == entry.id
    catalog.save()
    catalog.render_urls(url_file)
    assert "https://example.com/docs" not in url_file.read_text(encoding="utf-8")


def test_import_from_manifest(tmp_path, monkeypatch):
    catalog_path = tmp_path / "docy_sources.json"
    catalog_path.write_text('{"sources": []}', encoding="utf-8")
    url_file = tmp_path / ".docy.urls"
    monkeypatch.setattr(docy_server, "CATALOG_PATH", catalog_path)
    monkeypatch.setattr(docy_server, "URL_FILE_PATH", url_file)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": "Example Repo",
                    "source": "https://github.com/example/repo",
                    "description": "Example repository docs",
                    "tags": ["repo", "docs"],
                },
                {
                    "name": "API Reference",
                    "url": "https://docs.example.com/api",
                    "description": "API docs",
                },
                {
                    "name": "Internal",
                    "uri": "memory://internal",
                },
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    dry_run = docy_server._execute(
        "import_from_manifest",
        {"manifest_path": str(manifest), "tags": ["imported"], "dry_run": True},
    )
    assert dry_run["summary"]["created"] == 2
    assert dry_run["dryRun"] is True
    assert catalog_path.read_text(encoding="utf-8").strip() == '{"sources": []}'

    result = docy_server._execute(
        "import_from_manifest",
        {"manifest_path": str(manifest), "tags": ["imported"], "dry_run": False},
    )
    assert result["summary"]["created"] == 2
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert len(data["sources"]) == 2
    contents = url_file.read_text(encoding="utf-8")
    assert "https://github.com/example/repo" in contents
    assert "https://docs.example.com/api" in contents
