# Cost estimate (Azure)

**Estimate only.** Rough pay-as-you-go list prices for an EU region (West/North Europe), Linux,
USD, 730 hours a month, written in Week 1 without access to the account. Prices change by region
and over time: **verify every line in the Azure pricing calculator**
(<https://azure.microsoft.com/pricing/calculator/>) and update this table with the real numbers
and the date.

## Monthly estimate

| Item | Choice (plan 7.2) | Approx. USD / month | Notes |
|---|---|---|---|
| VM | B2s (2 vCPU, 4 GB) | ~35 | Running 24/7. Deallocated VMs cost no compute. |
| VM (alternative) | B2ms (2 vCPU, 8 GB) | ~70 | Only if Postgres + monitoring need the RAM (Week 5). |
| OS disk | 30 GB Standard SSD (E4) | ~2.5 | Premium SSD (P4) is ~5; Standard is enough here. |
| Data disk | 32 GB Standard SSD (E4), encryption at rest (platform keys) | ~2.5 | Billed even when the VM is deallocated. |
| Static public IP | Standard, static | ~3.5 | Billed while allocated, even with the VM stopped. |
| Blob Storage (backups) | ~20 GB, Cool or Hot LRS, second EU region | ~0.5 to 1 | Plus small transaction costs; GRS roughly doubles it. |
| Bandwidth (egress) | API traffic + backups to another region | ~0 to 2 | The first 100 GB/month of internet egress are free; inter-region transfer for backups is a few cents per GB. |
| Snapshots | none kept | 0 | Delete old snapshots (plan 7.2 operating rules). |
| **Total with B2s** | | **~45** | |
| **Total with B2ms** | | **~80** | |

Not included (free or not used): Azure DNS (optional, ~0.5 per zone), Communication Services
Email (pay per message, cents for our volume), Application Insights availability test (free
tier), GHCR and GitHub Actions (Student Pack), FCM (free), Let's Encrypt (free).

## What the credit covers

Azure for Students gives USD 100 (verify current terms). At ~45 USD/month with the VM running
all the time, the credit lasts **about two months**, less with B2ms. To stretch it:

- Deallocate the VM when nobody is working on it during development (portal: Stop). The data
  disk and static IP still cost ~6 USD/month together.
- Stay on B2s until monitoring (Week 5) shows memory pressure.
- Keep backups small (pgBackRest retention of two fulls) and in the Cool tier.
- Delete unused disks, public IPs and snapshots right away.
- Consider a cheaper burstable size with the same vCPU/RAM (for example the `B2als_v2` family) if
  the calculator shows it lower in our region; the images are multi-arch, so an ARM size works too.

## Budget alert

Created before any other resource (`Ionut/manual_steps.md` step 1): Cost Management budget on
the student subscription, for example 20 USD monthly, alerts at 50%, 80% and 100% of actual
cost plus 100% forecast, e-mail to Ionut. Cloud bills do not stop on their own. Check the
"Cost analysis" view weekly and record the real monthly figure here.

| Date | Real cost this month (USD) | Credit left (USD) | Notes |
|---|---|---|---|
| _fill in_ | | | |
