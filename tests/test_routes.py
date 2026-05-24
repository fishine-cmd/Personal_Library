def test_index_redirects_to_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_register_login_flow(client):
    resp = client.post("/auth/register", data={
        "username": "alice", "password": "pwd12345", "password2": "pwd12345",
    }, follow_redirects=False)
    assert resp.status_code == 302

    client.get("/auth/logout")

    resp = client.post("/auth/login", data={
        "username": "alice", "password": "pwd12345",
    }, follow_redirects=False)
    assert resp.status_code == 302


def test_document_crud(client):
    client.post("/auth/register", data={
        "username": "bob", "password": "pwd12345", "password2": "pwd12345",
    })
    # create
    resp = client.post("/documents/new", data={
        "title": "Test Paper",
        "document_type": "journal_article",
        "publication_year": "2024",
        "source_name": "Nature",
        "source_type": "journal",
        "publisher_name": "Springer",
        "authors_raw": "Alice | MIT | a@x.com\nBob | Stanford",
        "keywords_raw": "ml, graph",
        "abstract": "abc",
        "reading_status": "unread",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Test Paper".encode() in resp.data

    # list & search
    resp = client.get("/documents/?q=Alice")
    assert "Test Paper".encode() in resp.data

    # detail
    resp = client.get("/documents/1")
    assert resp.status_code == 200
    assert b"Springer" in resp.data
    assert b"graph" in resp.data

    # delete
    resp = client.post("/documents/1/delete", follow_redirects=True)
    assert resp.status_code == 200
