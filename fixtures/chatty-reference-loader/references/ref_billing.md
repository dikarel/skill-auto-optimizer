# Billing System Reference

## Overview

The Acme Corp Billing Service manages subscription lifecycle, invoice generation, payment processing, and revenue recognition. It integrates with Stripe as the primary payment processor.

## Pricing Tiers

| Tier | Monthly Price | Annual Price | Users | API Calls/hr |
|---|---|---|---|---|
| Starter | $29 | $290 | 1–5 | 1,000 |
| Growth | $99 | $990 | 6–25 | 5,000 |
| Business | $299 | $2,990 | 26–100 | 20,000 |
| Enterprise | Custom | Custom | Unlimited | Custom |

Annual plans are billed upfront and receive a 2-month discount (equivalent to ~17% off).

## Billing Cycle

- Monthly plans: billed on the same calendar day each month (subscription start date)
- Annual plans: billed once per year on the subscription anniversary
- Usage overages (API calls): billed in arrears at end of billing period
- Trial period: 14 days, no credit card required

## Invoice Generation

Invoices are generated:
1. Automatically at the start of each billing cycle
2. Immediately for one-time charges (seat additions, overages)
3. On plan upgrades (prorated difference)

Invoice format: PDF + JSON API. Delivered via email and available in the billing portal.

## Payment Processing

Supported payment methods:
- Credit / debit cards (Visa, Mastercard, Amex, Discover)
- ACH bank transfer (US only, $500+ invoices)
- Wire transfer (Enterprise only)
- Invoice (Net-30, Enterprise only)

Payment retries on failure:
1. Immediate retry
2. 3 days later
3. 7 days later
4. 14 days later → account suspended
5. 21 days later → account terminated

## Refund Policy

- Within 14 days of charge: full refund, no questions asked
- 14–30 days: prorated refund for unused period
- After 30 days: no refund except for documented billing errors
- Annual plans: prorated refund available within 30 days of annual charge

## Dunning Workflow

When payment fails:
1. Email notification to account owner and billing contacts
2. In-app banner displayed to all account users
3. Grace period: 21 days before service suspension
4. Data retention after suspension: 90 days before deletion

## Tax Handling

- US customers: sales tax collected based on billing address state
- EU customers: VAT collected based on country; EU VAT number required for B2B exemption
- Tax-exempt organizations: upload exemption certificate in billing portal

## Proration Rules

Upgrades: immediate; prorated charge for remaining days in cycle
Downgrades: effective at next billing cycle; no proration credit
Seat additions: prorated for remaining days
Seat removals: effective at next billing cycle
