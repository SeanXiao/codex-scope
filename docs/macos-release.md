# macOS Release Signing And Notarization

Codex Scope can now build a standard macOS release pipeline with:

- `Developer ID Application` signing
- Apple notarization via `xcrun notarytool`
- stapled `.app` and `.dmg`
- GitHub Release upload

## Required GitHub Secrets

Add these repository secrets before running `.github/workflows/macos-release.yml`:

- `MACOS_DEVELOPER_ID_P12_BASE64`
  Base64-encoded `.p12` certificate export for your Developer ID Application certificate.
- `MACOS_DEVELOPER_ID_P12_PASSWORD`
  Password used when exporting the `.p12`.
- `MACOS_KEYCHAIN_PASSWORD`
  Temporary CI keychain password.
- `MACOS_NOTARY_APPLE_ID`
  Your Apple ID email used for notarization.
- `MACOS_NOTARY_TEAM_ID`
  Your Apple Developer Team ID.
- `MACOS_NOTARY_APP_PASSWORD`
  An app-specific password for notarization.

## Local Signed Build

If your local Mac already has the certificate and notary profile configured, you can run:

```bash
CODEX_SCOPE_APP_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
CODEX_SCOPE_NOTARY_KEYCHAIN_PROFILE="codex-scope-notary" \
bash scripts/build_macos_app.sh
```

## CI Behavior

The GitHub Actions workflow will:

1. import the Developer ID certificate into a temporary keychain
2. store a `notarytool` keychain profile
3. build the app
4. sign the `.app`
5. build and sign the `.dmg`
6. notarize the `.dmg`
7. staple both `.app` and `.dmg`
8. verify with `spctl`
9. upload the notarized `.dmg` to the GitHub Release

## Result

Once the secrets are configured and the workflow succeeds, users downloading the macOS release should no longer see the common "app is damaged and can't be opened" Gatekeeper warning caused by unsigned or unnotarized binaries.
