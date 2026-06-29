from pathlib import Path


def test_get_rules(client, auth_headers):
    r = client.get('/api/v1/settings/rules', headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json()['data'], list)


def test_snapshot_create_list_and_restore(client, auth_headers, tmp_path):
    from app.routers import settings as settings_router
    from app.services.db_snapshot_service import DatabaseSnapshotService

    original_cls = settings_router.DatabaseSnapshotService
    settings_router.DatabaseSnapshotService = lambda: DatabaseSnapshotService(snapshot_dir=str(tmp_path))
    try:
        create = client.post('/api/v1/settings/snapshots', json={'label': 'testcase'}, headers=auth_headers)
        assert create.status_code == 200
        snapshot_name = create.json()['data']['name']
        assert 'testcase' in snapshot_name
        assert (Path(tmp_path) / snapshot_name).exists()

        listing = client.get('/api/v1/settings/snapshots', headers=auth_headers)
        assert listing.status_code == 200
        assert any(item['name'] == snapshot_name for item in listing.json()['data'])

        restore = client.post('/api/v1/settings/snapshots/restore', json={'name': snapshot_name}, headers=auth_headers)
        assert restore.status_code == 200
        assert restore.json()['data']['name'] == snapshot_name

        delete = client.request('DELETE', '/api/v1/settings/snapshots', json={'name': snapshot_name}, headers=auth_headers)
        assert delete.status_code == 200
        assert not (Path(tmp_path) / snapshot_name).exists()
    finally:
        settings_router.DatabaseSnapshotService = original_cls
