# deploy/ — GitOps manifests

Kustomize base for the `calendar-sync` CronJob, reconciled by ArgoCD. Modeled on
the GEH / whatsintown git-lane flow: CI pins an **immutable image tag** onto a
generated deploy branch, ArgoCD rolls it out, and rollback is a git revert.

## Flow

```
push to main
  └─ .github/workflows/deploy.yaml
       test → build+push  ghcr.io/dimonb/calendar-sync/calendar-sync:<sha>
       promote            sed  newTag: latest → newTag: <sha>
                          commit + force-push  →  deploy/main branch
ArgoCD (k8s-dibot gitops/apps/calendar-sync.yaml, targetRevision: deploy/main)
  └─ renders deploy/  →  CronJob runs the pinned <sha>
```

- **`main`** keeps the inert placeholder `newTag: latest` in
  `kustomization.yaml` — no image-bump churn in review history.
- **`deploy/main`** is CI-owned. Never commit to it by hand; the `promote` job
  force-updates it (`--force-with-lease`) on every push to `main`.
- The deployed tag is immutable (`:<sha>`), so the CronJob uses
  `imagePullPolicy: IfNotPresent`.

## Rollback

Point `deploy/main` back at an earlier promotion:

```bash
git push origin <previous-promote-commit>:deploy/main --force-with-lease
```

or revert the bump commit on `deploy/main`. ArgoCD reconciles within a few
minutes.

## Contents

| File | What |
|------|------|
| `kustomization.yaml` | resources + `images:` tag pin (the promote target) |
| `cronjob.yaml` | the `*/5` sync CronJob |
| `pvc.yaml` | adopted RWO claim — OAuth tokens + sqlite mapping DB |
| `externalsecret.yaml` | config/creds/DSN from Infisical `/calendar-sync` via ESO |

## Secrets

Not in git. `ExternalSecret`s pull from the self-hosted Infisical store
`infisical-secret-store-calendar-sync` (folder `/calendar-sync`): keys
`CALENDAR_SYNC_CONFIG`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_CLIENT_SECRET2`,
`UPTRACE_DSN`.
