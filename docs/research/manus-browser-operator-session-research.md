# Manus Browser Operator Session Research

## Scope

This note records official Manus materials consulted on 14 August 2026 for the Career OS authenticated-browser integration. It distinguishes the **Browser Operator / My Browser** local-browser mechanism from the separate **Cloud Browser** product so the implementation does not make unsupported session-persistence claims.

## Supported Browser Operator facts

The official Browser Operator documentation states that the extension operates in the user's local Chrome or Edge browser, using existing local logins, active tabs, and the local IP address. The user enables the **My Browser** connector, installs the extension, and explicitly authorizes a session when Manus requests control. Each task requires user permission; activity is visible in a dedicated tab group and can be stopped by closing the tab.

The official Trust Center states that Browser Operator runs in the user's browser context, that authentication remains in the local browser, and that Manus does not store passwords. It specifies revocation by toggling off **My Browser** in Manus Settings → Connectors, optionally uninstalling the extension. The My Browser information page also instructs users to close sensitive tabs to revoke access and to stop first when uncertain.

The materials describe optional cross-browser task access: after enabling **Allow Cross-Browser Tasks** in the My Browser connector configuration, Manus can drive authorized browser sessions linked to the account. This is still a supported local-browser authorization mechanism, not permission for Career OS to extract session material.

## Persistence boundary

The official Browser Operator sources establish that the authenticating browser state is the user's own local browser session. They do **not** disclose an exact on-disk Browser Operator profile location or promise that a browser session survives task termination, browser restart, Manus logout, website logout, or the target site's own session-expiry policy. Career OS must therefore treat profile persistence as platform-managed and unknown, never as an application-controlled guarantee.

Cloud Browser is different. The official Trust Center describes Cloud Browser as securely remembering cookies and local storage across future tasks and devices, with sandbox data deleted after the stated retention window. That behavior must not be attributed to Browser Operator and must not be used by Career OS to export, inspect, or copy Cloud Browser session data.

## Career OS integration rules derived from sources

1. Career OS may request that a Manus browser task use the supported local My Browser context.
2. Career OS must pass only application identity, verified URL, approved answers, and the exact JD-tailored resume evidence to its browser task; it must not accept or serialize passwords, OTP/MFA codes, cookies, tokens, authentication headers, or browser storage.
3. Browser preflight must return `BROWSER_UNAVAILABLE` / `REVIEW_REQUIRED` if the verified URL is not authenticated or the operator context is unavailable. It must never attempt login, session repair, credential scraping, or authentication bypass.
4. Runtime state, GitHub workflow artifacts, application manifests, Notion records, logs, and repository files must retain only a non-secret browser-session status and blocker reason, never browser state.
5. User-visible operations for reconnecting are: enable My Browser, install/enable the extension, sign in directly in the local browser, authorize when Manus asks, and optionally enable cross-browser tasks in the connector settings. These are user-controlled actions.
6. User-visible operations for revocation are: stop/close the dedicated task tab, close sensitive tabs, disable My Browser in Connectors, optionally uninstall the extension, and separately log out from the target website in the user browser. Career OS has no API or code path to revoke or clear browser authentication.

## Sources

1. [Manus Browser Operator documentation](https://manus.im/docs/integrations/manus-browser-operator)
2. [Browser Operator feature documentation](https://manus.im/docs/features/browser-operator)
3. [Manus Browser Operator Trust Center FAQ](https://trust.manus.im/faq?s=uhpg2z3dme2xjh0y57ewbs)
4. [My Browser instructions](https://manus.im/my-browser)
5. [Cloud Browser documentation, included only to distinguish its separate persistence model](https://manus.im/docs/features/cloud-browser)
6. [Browser Operator connector guide](https://manus.im/blog/deep-dive-browser-operator-connector)
