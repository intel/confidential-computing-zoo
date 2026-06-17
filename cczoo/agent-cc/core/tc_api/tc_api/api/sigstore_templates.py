# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""HTML templates for the Sigstore OIDC interactive login pages."""

from html import escape


def render_interactive_login_page(
    *,
    safe_operation: str,
    remote_token_url: str,
    callback_token_url: str,
    oob_token_url: str,
    submit_url: str,
    initial_status: str,
    initial_auth_url: str,
    initial_session_id: str,
    initial_flow: str,
    sample_payload: str,
    initial_session_id_json: str,
    initial_flow_json: str,
) -> str:
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>Sigstore OIDC Login</title>
    <style>
        body {{ font-family: sans-serif; margin: 2rem auto; max-width: 860px; line-height: 1.5; }}
        textarea, pre {{ width: 100%; box-sizing: border-box; }}
        textarea {{ min-height: 12rem; }}
        <button type="button" onclick="startLogin('server-callback')">Start Direct Callback Login</button>
        button {{ margin-right: 0.75rem; margin-bottom: 0.75rem; padding: 0.6rem 1rem; }}
    <h2>Status</h2>
    <pre id="status">{escape(initial_status, quote=False)}</pre>
<body>
    <pre id="auth_url">{escape(initial_auth_url, quote=False)}</pre>
    <p>This page helps you obtain a short-lived OIDC token for the <strong>{safe_operation}</strong> operation without setting any environment variables.</p>
    <p>If you came here from a missing-token API response, this page can continue the same login session without making you assemble a JSON request manually.</p>
    <p>Choose the login mode that matches your environment. Use SSH/Remote Mode when your browser cannot reach this server directly after login. Use Direct Callback Mode only when your browser can open this server's callback URL.</p>
    <p>
        <button type="button" onclick="startLogin('copy-url')">Start SSH/Remote Login</button>
    <pre id="status">{escape(initial_status, quote=False)}</pre>
    <p>
    <pre id="auth_url">{escape(initial_auth_url, quote=False)}</pre>
        <button type="button" onclick="startLogin('oob')">Start OOB Login</button>
    <pre id="status">Idle</pre>
    <h2>Login URL</h2>
    <pre id="auth_url">Not started</pre>
    <h2>Final Browser URL</h2>
    <textarea id="redirect_url" spellcheck="false" placeholder="For SSH/Remote Mode: after login, paste the final browser URL that starts with https://oauth2.sigstore.dev/auth/callback here"></textarea>
    <p>
        <button type="button" onclick="completeRemoteLogin()">Submit Final URL</button>
    </p>
    <h2>Identity Token</h2>
    <textarea id="token" spellcheck="false" placeholder="Token will appear here after login completes"></textarea>
    <h2>Verification Code</h2>
    <textarea id="verification_code" spellcheck="false" placeholder="For OOB Mode: paste the verification code shown by Sigstore here"></textarea>
    <p>
        <button type="button" onclick="completeOobLogin()">Submit Verification Code</button>
    </p>
    <h2>Retry Example</h2>
    <pre id="retry">curl -X POST "http://127.0.0.1:8000/api/build-package" -H "Content-Type: application/json" -d '{sample_payload}'</pre>
    <script>
        let pendingSessionId = {initial_session_id_json};
        let pendingFlow = {initial_flow_json};

        function updateRetry(identityToken) {{
            const retry = document.getElementById('retry');
            retry.textContent = 'curl -X POST "http://127.0.0.1:8000/api/build-package" -H "Content-Type: application/json" -d ' + JSON.stringify({{
                dockerfile: 'FROM ghcr.io/1186258278/openclaw-zh:nightly',
                app_binary: 'dGVzdCBiaW5hcnkK',
                configs: ['Y29uZmlnCg=='],
                data: ['ZGF0YQo='],
                encrypt: true,
                user_id: 'test-user',
                identity_token: identityToken,
            }});
        }}

        window.addEventListener('message', (event) => {{
            if (event.origin !== window.location.origin) {{
                return;
            }}
            if (!event.data || event.data.sigstore_login_result !== true) {{
                return;
            }}
            const status = document.getElementById('status');
            const tokenBox = document.getElementById('token');
            status.textContent = JSON.stringify(event.data, null, 2);
            if (event.data.status === 'token_ready') {{
                tokenBox.value = event.data.identity_token;
                updateRetry(event.data.identity_token);
            }}
        }});

        async function startLogin(flow) {{
            const status = document.getElementById('status');
            const authUrl = document.getElementById('auth_url');
            const tokenBox = document.getElementById('token');
            const redirectUrl = document.getElementById('redirect_url');
            status.textContent = 'Starting Sigstore OIDC login...';
            tokenBox.value = '';
            redirectUrl.value = '';
            try {{
                let loginUrl = '{remote_token_url}';
                if (flow === 'server-callback') {{
                    loginUrl = '{callback_token_url}';
                }} else if (flow === 'oob') {{
                    loginUrl = '{oob_token_url}';
                }}
                const response = await fetch(loginUrl);
                const data = await response.json();
                if (!response.ok) {{
                    status.textContent = JSON.stringify(data, null, 2);
                    return;
                }}
                if (data.status === 'token_ready') {{
                    tokenBox.value = data.identity_token;
                    status.textContent = JSON.stringify(data, null, 2);
                    authUrl.textContent = 'Used cached token';
                    updateRetry(data.identity_token);
                    return;
                }}
                pendingSessionId = data.session_id;
                pendingFlow = data.flow;
                authUrl.textContent = data.auth_url;
                status.textContent = JSON.stringify(data, null, 2);
                window.open(data.auth_url, '_blank', 'noopener');
            }} catch (error) {{
                status.textContent = String(error);
            }}
        }}

        async function completeRemoteLogin() {{
            const status = document.getElementById('status');
            const tokenBox = document.getElementById('token');
            const redirectUrl = document.getElementById('redirect_url').value.trim();
            if (!pendingSessionId) {{
                status.textContent = 'Start a login flow first to create a Sigstore session.';
                return;
            }}
            if (pendingFlow !== 'copy-url') {{
                status.textContent = 'The current session expects automatic server callback. Start SSH/Remote Login to use pasted final URLs.';
                return;
            }}
            if (!redirectUrl) {{
                status.textContent = 'Paste the final browser URL before submitting.';
                return;
            }}
            status.textContent = 'Finishing Sigstore login from the pasted browser URL...';
            try {{
                const response = await fetch('{submit_url}', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        operation: '{safe_operation}',
                        session_id: pendingSessionId,
                        redirect_url: redirectUrl,
                    }}),
                }});
                const data = await response.json();
                if (!response.ok) {{
                    status.textContent = JSON.stringify(data, null, 2);
                    return;
                }}
                tokenBox.value = data.identity_token;
                status.textContent = JSON.stringify(data, null, 2);
                updateRetry(data.identity_token);
            }} catch (error) {{
                status.textContent = String(error);
            }}
        }}

        async function completeOobLogin() {{
            const status = document.getElementById('status');
            const tokenBox = document.getElementById('token');
            const verificationCode = document.getElementById('verification_code').value.trim();
            if (!pendingSessionId) {{
                status.textContent = 'Start a login flow first to create a Sigstore session.';
                return;
            }}
            if (pendingFlow !== 'oob') {{
                status.textContent = 'The current session is not using OOB. Start OOB Login to use verification codes.';
                return;
            }}
            if (!verificationCode) {{
                status.textContent = 'Paste the verification code before submitting.';
                return;
            }}
            status.textContent = 'Finishing Sigstore login from the pasted verification code...';
            try {{
                const response = await fetch('{submit_url}', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        operation: '{safe_operation}',
                        session_id: pendingSessionId,
                        verification_code: verificationCode,
                    }}),
                }});
                const data = await response.json();
                if (!response.ok) {{
                    status.textContent = JSON.stringify(data, null, 2);
                    return;
                }}
                tokenBox.value = data.identity_token;
                status.textContent = JSON.stringify(data, null, 2);
                updateRetry(data.identity_token);
            }} catch (error) {{
                status.textContent = String(error);
            }}
        }}
    </script>
</body>
</html>
"""


def render_callback_page(*, title: str, payload_json: str) -> str:
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>{escape(title, quote=True)}</title>
    <style>
        body {{ font-family: sans-serif; margin: 2rem auto; max-width: 860px; line-height: 1.5; }}
        textarea, pre {{ width: 100%; box-sizing: border-box; }}
        textarea {{ min-height: 12rem; }}
        pre {{ background: #f5f5f5; padding: 1rem; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>{escape(title, quote=True)}</h1>
    <p>This window can be closed. The opener page will receive the login result automatically.</p>
    <pre id="payload"></pre>
    <script>
        const payload = {payload_json};
        document.getElementById('payload').textContent = JSON.stringify(payload, null, 2);
        if (window.opener) {{
            window.opener.postMessage(payload, window.location.origin);
        }}
    </script>
</body>
</html>
"""
