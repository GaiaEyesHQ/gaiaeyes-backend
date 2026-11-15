# Mod Panic catalog-to-review workflow

This package automatically reads the Mod Panic Shopify catalog when invoked, groups product formats by artwork, creates Facebook/Instagram captions and JPEG layouts, and updates a persistent local review queue. **It cannot publish Mod Panic posts.** No scheduler, deployment, Shopify mutation, image upload, or Meta authorization is performed by this workflow. The existing Gaia Eyes production workflows and EarthScope publisher remain unchanged.

## Run locally

Use Python 3.11 and the repository's existing `requests` and `Pillow` dependencies. Run from the repository root:

```sh
python -m unittest discover -s bots/shared_social -t . -p 'test_*.py' -v
python -m bots.shared_social.sync_drafts verify
python -m bots.shared_social.sync_drafts sync --output /path/to/private/modpanic-review
```

For verification and synchronization, inject `MOD_PANIC_SHOPIFY_CLIENT_ID` and `MOD_PANIC_SHOPIFY_CLIENT_SECRET` from a local secret manager or protected runner environment. They belong to the dedicated **Mod Panic Catalog Reader** app, installed on the verified Mod Panic store with **only `read_products`**. The app and store must belong to the same Shopify organization for this client-credentials flow. Do not put credentials in command arguments, files committed to Git, screenshots, or logs.

The reader obtains a short-lived access token from the pinned store's OAuth endpoint using a form-encoded client-credentials request. Credentials go only in the request body, never the URL. Tokens remain in process memory and are renewed at least 60 seconds before expiry. Token responses are limited to 64 KiB, checked for exactly `read_products` and a bounded lifetime, and never logged or written to disk. The reader separately checks the actual installation scopes and store identity before reading products. An authentication/renewal failure stops the operation; it never reuses an expired token or saves a partial catalog.

For an interactive local connection check, run `python -m bots.shared_social.sync_drafts verify --prompt`. Both credential fields are entered without echo and are used only for that process. The command refuses noninteractive input or a terminal that cannot hide the input. It prints only the pinned store IDs/domain, `read_products`, and disabled publishing status; it does not fetch products, download media, or update the queue. For a full refresh with the same private prompts, run `python -m bots.shared_social.sync_drafts sync --prompt --output /path/to/private/modpanic-review`. The refresh prints stage/count progress to stderr, without credentials or product text; stdout remains the JSON result. GitHub cannot reveal stored secret values, and GitHub secrets are not automatically available to local commands.

An explicitly supplied legacy `MOD_PANIC_SHOPIFY_READ_TOKEN` is still supported as an alternative. Supplying both authentication modes, or an incomplete client-credential pair, fails closed. Broad connector/admin tokens are deliberately rejected. The existing Autobot `SHOPIFY_ACCESS_TOKEN` has broad write permissions and is **not used or changed**. There is no fallback to `SHOPIFY_*`, `FB_*`, or Gaia Eyes credentials.

The reader is pinned to `oops-hand-sanitizer.myshopify.com`, shop ID `gid://shopify/Shop/41637576867`, and API version `2026-10`. The Shopify connector confirmed that this store is named Mod Panic. Identity and granted scopes are checked before reading products. Only two fixed GraphQL **queries** are allowed; GraphQL uses HTTP POST but neither operation is a mutation. The additional OAuth POST only obtains an access token. The reader retrieves all active products in bounded cursor pages, rejects repeated cursors/IDs and incomplete/error responses, and retries only throttling/server failures with bounded backoff. It never returns a partial snapshot as complete. Requests use timeouts, bounded response sizes, no redirects, and no inherited proxies or `.netrc` credentials.

Open `review.html` in the output directory. It contains both platform captions/images, product links for every group, review status, draft ID, exact revision, and the last successful refresh time and product counts. Reload the page after a refresh. `review.json` provides the same content as data. `queue.sqlite3` is the authoritative durable queue and review history; **retain and back up the entire directory** between invocations. Deleting the database loses deduplication/review history. Concurrent local sync/review writers are serialized with a filesystem lock, including the live catalog fetch, so overlapping refreshes cannot apply their snapshots out of order. This is a trusted single-user/local-runner tool, not a multi-user authorization service.

An existing trusted snapshot can be replayed with `--catalog /path/to/catalog.json`. It must be an envelope containing `schema_version: 1`, `brand: mod_panic`, the pinned `shop_id` and `shop_domain`, `complete: true`, and a `products` array with the queried fields. Limited fixtures intentionally set `complete: false` and cannot update the queue. Snapshot replay is explicit and cannot be combined with `--prompt`; normal runs automatically read Shopify. Live snapshots record `fetched_at`; legacy snapshots without that timestamp are clearly labeled as having an unknown retrieval time, even when replayed today.

## Artwork grouping and drafts

- Product variants stay within their parent product. Different product formats sharing an artwork key yield one artwork draft, with separate Facebook and Instagram assets/captions.
- Normalized format prefixes/suffixes cover mugs, stickers, magnets, wall prints, coasters, towels, clothing, bags, and carriers. Legacy price/copy suffixes use the cleaner product title. Words inside artwork names and distinct colorways remain intact.
- Explicit artwork identity takes precedence: use `--artwork-map /path/to/artwork-map.json` (product ID or handle → stable artwork slug), or read an existing `artwork:<slug>` product tag. This tool never writes tags. Conflicting tags fail closed. Preserve canonical keys when mapping existing designs, especially already-used artwork.
- Naming heuristics cannot prove two differently named artworks are identical or two identically named artworks are different. Review the grouped product links and image/title match; use explicit mappings for ambiguous cases before recording approval. No visual similarity inference or invented catalog data is used.
- Only active Mod Panic products with a matching public `modpanic.com/products/...` URL and media inside this store's Shopify CDN directory qualify. Unpublished, wrong-brand, missing-media, and invalid-URL products are excluded. When one product format is deleted, its link leaves the group and the updated draft needs review. When all eligible products for an artwork disappear, its draft is withdrawn and cannot be approved. These changes happen on the next successful full sync; no schedule is enabled.
- Captions use actual product titles and verified storefront URLs. They make no stock, price, manufacturing-origin, originality, or link-in-bio claims. Product text is treated as data; HTML output is escaped and uses a restrictive content policy with local images only.
- Facebook images are 1200×630; Instagram images are 1080×1350. The actual catalog photo is contained without cropping the artwork. JPEG exports flatten transparency and omit source EXIF metadata. Image downloads are unauthenticated, restricted to the pinned CDN path, nonredirecting, size/dimension limited, and decoded only as JPEG/PNG/WebP. No AI image invention or upload occurs.

## Review safeguards

New/changed drafts start as `needs_review`. Stable artwork IDs and database uniqueness prevent reruns from adding another draft for the same artwork. Identical reruns preserve decisions. Product membership, titles, URLs, captions, and rendered image hashes are all included in the revision; changes invalidate approval. Missing response fields, a failed catalog page, or a rendering failure leave existing queue decisions and the last successful refresh record unchanged. A complete empty catalog correctly withdraws all active drafts. Withdrawn artwork returning to the catalog receives a new review generation, even if its content is identical, so a pre-deletion revision cannot approve it.

To record a local decision after inspecting both platform drafts, copy its full ID/revision from `review.html` or `review.json`:

```sh
python -m bots.shared_social.sync_drafts review \
  --output /path/to/private/modpanic-review \
  --draft-id REVIEWED_ID --revision REVIEWED_SHA256 \
  --decision approved --reviewer 'Your name'
```

Use `--decision rejected` to reject the exact revision. The command validates the revision and both image hashes, then records reviewer, decision, and time in an append-only application audit table. Local filesystem access is the trust boundary; this is not a cryptographic proof of a person's identity. Hand-editing `review.json` cannot authorize anything. Local approval is **not publishing authorization**: the shared Mod Panic Facebook path is hard-disabled even with `approved=True`, and Instagram remains disabled. No queue component imports the Meta publisher or reads Meta credentials.

`--used-keys /path/to/used-artworks.json` imports a JSON array of artwork keys already used elsewhere. These remain durably suppressed, including through catalog removal/reappearance. No publishing history is invented. Approval alone never marks artwork as published. A future publisher needs independent account binding, authorization, durable publish-attempt/idempotency records, outcome reconciliation, and explicit rollout approval.

Font/Pillow differences between machines may change JPEG hashes and correctly require a fresh review. Orphan image files from failed/replaced renders are harmless and never make a draft publishable. SQLite is authoritative if export writing is interrupted; rerun sync to refresh HTML/JSON. Use a persistent trusted local filesystem, not a temporary CI workspace, for real queue history.

## Workflow status

Reference: [Shopify client-credentials authentication](https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant), [GitHub manual workflow requirements](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

`.github/workflows/modpanic_social_preview.yml` runs the isolated tests for pull requests touching this package or its workflow, and supports manual dispatch, with `contents: read` and no schedule. Tests never load secrets. The optional manual `verify_shopify` input defaults to false. Only on an explicitly selected manual dispatch does a separate job run after the tests pass and receive `MOD_PANIC_SHOPIFY_CLIENT_ID` and `MOD_PANIC_SHOPIFY_CLIENT_SECRET`, scoped to its verification step. It checks authentication, store identity, and permissions without importing products, touching the queue, or loading Meta/Gaia Eyes credentials. Checkout credentials are not persisted. The live verification job cannot run for a pull request.

GitHub requires a `workflow_dispatch` workflow to exist on the default branch before it can be launched. The existing preview file was found on `feature/modpanic-multibrand-social` but returned 404 on `main`; no default-branch change or merge was performed. Use the local private-input check while that limitation remains. No live catalog job or schedule is enabled. Future recurring synchronization also needs persistent queue storage; an ephemeral GitHub job is not a durable review queue.

## Verification performed for this implementation

The connected Shopify Admin reader returned all 413 active products across nine pages on November 14, 2026 (America/Chicago). Of those, 411 had public storefront URLs and 410 had eligible store media. The two unpublished products and one product without eligible media were excluded. Actual Mississippi Blue Wave products are captured in the regression fixture: seven formats collapse to one artwork. Fixture records contain public product fields only, with no credentials.

The user installed the dedicated Mod Panic Catalog Reader with `read_products`, saved its two client credentials in GitHub, and entered them privately for a live full refresh. The resulting queue records a completed refresh at **2026-11-15 01:40:04 America/Chicago** (07:40:04 UTC), with catalog retrieval at 07:39:16 UTC: 413 products checked, 410 eligible products, and 142 artwork groups. The refresh passed the reader's required live token exchange, pinned-shop identity, and exact-scope checks before reading the catalog. Credential values were not extracted from GitHub or persisted by the checker/refresh command.

Post-refresh verification checked SQLite integrity, all stored content revisions, JSON/HTML consistency, unique product membership, and all 284 image hashes, JPEG formats and dimensions. All 142 active revisions matched the previous snapshot-based drafts; there were no new/removed artwork groups, no duplicate products and no approvals. The 33 older withdrawn rows remain hidden history. This is observed output from the user-launched dedicated-app refresh, not merely a mock or connection-only check. Both fixed queries were previously validated against the 2026-10 Shopify schema; OAuth renewal/failure cases remain covered with mocked transport.

The isolated suite passes 73 tests, including private credential entry, OAuth renewal, full command-to-queue integration, partial-format deletion, complete withdrawal, reappearance, stale approvals, complete-empty catalogs, malformed responses, second-page failures, image failures, serialized live reads, and refresh-history consistency. Tests use fake transport and temporary queues; they do not modify Shopify or existing review decisions.

## Remaining Meta authorization steps

The user has verified the following in Meta's debugger and read-only Graph API Explorer calls: app `3578786055634077`, Facebook Page `109717430794544` (Mod Panic), Instagram account `17841440619347031` (`modpanic`), a valid Page token with `pages_manage_posts` and `instagram_content_publish`, and expiry on January 13, 2027. These are user-reported checks, not a live publishing test. The user reports saving `MOD_PANIC_FB_ACCESS_TOKEN` in GitHub; the draft sync never uses it. The existing client uses the **Facebook Login** path. Before a future publishing rollout:

1. Confirm the intended Mod Panic Facebook Page and connected Instagram **Business or Creator** account. Confirm the authorizing person has the required Page tasks; do not reuse Gaia Eyes Page/account IDs or tokens.
2. Configure the relevant Meta app and Facebook Login for Business. Request `pages_show_list` and `instagram_basic` for discovery. For Instagram publishing, verify `instagram_content_publish` and `pages_read_engagement`; Meta documents additional `ads_management`/`ads_read` requirements for applicable Business Manager role arrangements. For Facebook publishing, verify `pages_manage_posts` and the additional Page permissions/tasks required by the selected endpoints and current app configuration.
3. Complete required app review/Advanced Access for the intended users, business verification where required, and Page Publishing Authorization if Meta requires it. Check token validity, expiry, granted permissions, and asset restrictions with read-only calls. Resolve the Page through `/me/accounts` and its linked account through `/{page-id}?fields=instagram_business_account`.
4. Only after verification, configure separate `MOD_PANIC_FB_PAGE_ID`, `MOD_PANIC_IG_USER_ID`, and `MOD_PANIC_FB_ACCESS_TOKEN` in protected secret storage. These are unused by the draft sync. Do not send secrets through chat.
5. Before any future rollout, implement/review Instagram processing checks and retry/idempotency handling, separately authorize media hosting (Meta needs publicly accessible image URLs), bind approval to exact brand/account/platform/content, and obtain explicit approval for the first live posts. Local approval does not enable these steps.

References: [Shopify product pagination](https://shopify.dev/docs/api/admin-graphql/2026-10/queries/products), [Shopify installation scopes](https://shopify.dev/docs/api/admin-graphql/2026-10/queries/currentAppInstallation), [Shopify image scope alternatives](https://shopify.dev/docs/api/admin-graphql/2026-10/objects/MediaImage), [Meta account discovery](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-facebook-login/get-started), [Meta Instagram publishing requirements](https://developers.facebook.com/documentation/instagram-platform/content-publishing/), [Meta Page publishing requirements](https://developers.facebook.com/documentation/pages-api/posts).
