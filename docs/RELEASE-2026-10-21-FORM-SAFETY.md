# Keep submitted form edits safe

A slow profile save left fields and the dialog controls active. Typing after
submission was silently discarded when the earlier request completed. Reproduced
in desktop and mobile Chrome against the previous release; the pending-save
regression fails before the fix.

Submitted form data is captured before controls are disabled (disabled controls
are otherwise omitted by FormData). Inputs, selects and buttons in that dialog
pause until the action finishes. Escape and backdrop clicks cannot discard the
pending form. A status message announces work, and failures preserve the values,
restore each original disabled state and permit an explicit retry. Successful
next-step dialogs remain usable; programmatic completion can close the old form.

Validation requires both the exact Sites source and canonical/public mirror:
Ruff, offline Python, deterministic zero-model evaluation, JavaScript checks and
tests, production build, dependency audit and desktop/mobile form flows. No real
authentication, email, profile or scan is used in browser fixtures. Native live
asset/access checks and synthetic live UI checks are recorded in automation
memory; they do not prove real Cognito sign-in or an AWS backend rollout.

Cost: browser state only, no extra API requests, inference, sources, polling,
services, storage, retention, schedules, quotas or spending changes. No material
expected increase. Production rules mode, Bedrock denial and zero model ceilings
remain in force. No backend/schema/configuration changes. Broader older canonical
frontend/backend changes are excluded; publish only the current Sites source plus
this reviewed patch. Preserve public audience and existing project identity.
Rollback: redeploy saved Sites v102
appgprj_6a9fa33453988191895d1c0403f10071~appgver_1a5169c4b3a88191976a1a970f4e0341.
