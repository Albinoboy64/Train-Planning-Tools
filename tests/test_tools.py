    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("LOCALAPPDATA", d)
        monkeypatch.setenv("TPT_COMPACT", "0")
        try:
            import cwn_compare.gui as g
