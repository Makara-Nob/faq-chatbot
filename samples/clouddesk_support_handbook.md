# CloudDesk Support Handbook

Internal reference for the support team. Last reviewed: March 2026.
Contact the platform team on #clouddesk-help for anything not covered here.

## Plans and pricing

CloudDesk is sold in three tiers. The Starter plan costs $19 per user per month
and includes up to 5 seats, 10 GB of shared storage, and email support. The
Business plan costs $49 per user per month, raises the seat limit to 100, gives
100 GB of storage, and adds priority support with a four-hour response target.
The Enterprise plan is quoted individually and requires an annual contract.

All prices exclude VAT. Customers in the EU are charged VAT at their local rate
unless they supply a valid VAT registration number at checkout.

Annual billing is discounted by 20 percent compared with paying monthly. A
customer switching from monthly to annual mid-cycle receives a prorated credit
applied to the first annual invoice.

## Billing and invoices

Invoices are generated on the first day of each billing period and emailed to
the account's billing contact. They are also available under Settings, Billing,
Invoice history, where they can be downloaded as PDF.

We accept Visa, Mastercard, and American Express. Bank transfer is available on
the Enterprise plan only, with payment terms of net 30.

If a card payment fails, the system retries after 3 days, then again after 7
days. After the third failed attempt the workspace is downgraded to read-only.
Data is retained for 60 days after downgrade, and nothing is deleted during
that window.

To update the card on file, an account owner opens Settings, Billing, Payment
method. Admins without the owner role cannot change payment details; this is
deliberate and cannot be overridden by support.

## Refunds and cancellation

Customers may cancel at any time from Settings, Billing, Cancel subscription.
Cancellation takes effect at the end of the current billing period, and the
workspace stays fully usable until then.

Refunds are issued for annual plans cancelled within 30 days of purchase.
Monthly plans are not refunded, since cancelling already stops the next charge.
Approved refunds are returned to the original payment method and take 5 to 10
business days to appear, depending on the customer's bank.

Support agents can approve refunds up to $500. Anything above that needs sign
off from the finance team; open a ticket in the #finance-approvals channel.

## Accounts and access

A password reset is triggered from the sign-in page by selecting Forgot
password. The reset link stays valid for 60 minutes and can only be used once.
If the link expires the customer simply requests a new one.

Two-factor authentication is optional on Starter and Business, and mandatory on
Enterprise. Supported second factors are authenticator apps and hardware
security keys. We do not support SMS codes, because they are vulnerable to SIM
swapping.

Single sign-on through SAML is available on Business and Enterprise. Okta,
Entra ID, and Google Workspace are tested and documented; other SAML providers
usually work but are unsupported.

If a customer loses access to both their second factor and their recovery
codes, identity must be verified by video call with an account owner before
support can reset the factor. There is no exception to this, including for
Enterprise customers.

## Data, export, and deletion

Customers can export their entire workspace from Settings, Data, Export. The
export runs in the background and produces a ZIP archive containing JSON files
and any uploaded attachments. Large workspaces can take several hours, and the
download link is emailed when the archive is ready. The link expires after 7
days.

Deleting a workspace is irreversible. Once confirmed, data is removed from
production within 24 hours and purged from backups within 35 days.

Customer data is stored in Frankfurt for EU accounts and in Virginia for
everyone else. The storage region is chosen when the workspace is created and
cannot be changed afterwards without a full export and re-import.

## API and rate limits

The public API is REST over HTTPS and is authenticated with a bearer token
generated under Settings, Developer, API tokens. Tokens inherit the permissions
of the user who created them.

Rate limits are 60 requests per minute on Starter, 600 per minute on Business,
and negotiated on Enterprise. Exceeding the limit returns HTTP 429 with a
Retry-After header. Clients should back off rather than retrying immediately.

Webhooks are delivered at least once, so consumers must be idempotent. A failed
delivery is retried with exponential backoff for up to 24 hours before the
endpoint is marked unhealthy.

## Support hours and escalation

Standard support runs Monday to Friday, 9am to 6pm Central European Time.
Priority support on the Business plan targets a first response within four
working hours. Enterprise customers have 24 by 7 coverage for incidents that
affect production availability.

A customer reporting a complete outage should be escalated immediately to the
on-call engineer through PagerDuty, without waiting for triage. Anything
involving suspected unauthorised access to customer data goes to the security
team the same way, and must never be handled by support alone.
