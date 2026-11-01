"""Synthetic TestClient consent for isolated auth tests, never a real user action."""
def start_with_test_consent(client,provider='google'):
    version=client.get('/api/legal').json()['version']
    return client.post(f'/api/auth/{provider}/start',data={'terms_agreed':'yes','policy_version':version},headers={'origin':str(client.base_url).rstrip('/')},follow_redirects=False)
