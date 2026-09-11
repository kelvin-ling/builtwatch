# Custom domain cutover

Current hosting is hybrid: Cognito, DynamoDB, Lambda, Strands/Bedrock and scheduled
monitoring are in AWS. The website, authenticated gateway and D1 session/limit state are
hosted by Sites on Cloudflare. A new domain does not move those services to AWS.

The preferred public hostname is `builtwatch.org`, attached to the existing Sites project.
The original Sites hostname remains available as a fallback. The supported setup preserves
the existing Site and AWS accounts.

Once the owner supplies their purchased hostname:

1. Attach that exact hostname to the published Site. Use the DNS and validation records
   returned by the Sites custom-domain operation. It supplies CNAME targets for subdomains,
   apex A targets when applicable, and ownership/certificate validation records.
2. Set those records in the owner's Cloudflare DNS zone using authorized access. Preserve
   unrelated DNS and email records. Verify DNS, domain status and HTTPS activation through
   the Sites domain-status operation; a DNS record alone is not a completed cutover.
3. Test the custom hostname: public demo, registration/sign-in, existing inventory,
   same-origin writes, rate limits, owner isolation, bulk import and agent setup. API
   calls use relative URLs and current-origin CSRF checks. Cognito password authentication
   uses the same backend pool; no user-data migration is needed. Host-only session cookies
   do not transfer: users sign in again. Keep the original Site URL working during testing.
4. Update canonical links in the offline demo and cost-warning email; newly generated
   agent connection instructions should use the new website origin. Existing agent
   endpoints can continue using the old address while it remains available. Publish the
   preferred URL only after verification. Do not promise instantaneous DNS/TLS activation.

An all-AWS frontend/gateway migration would be a separate infrastructure change, including
session and limiter storage. It is not necessary just to use the custom domain. A domain
purchase and any provider-level hosting charges are separate from estimated model usage.
