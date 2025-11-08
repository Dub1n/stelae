from pathlib import Path

from stelae_lib.docy_catalog import DocyCatalog


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
