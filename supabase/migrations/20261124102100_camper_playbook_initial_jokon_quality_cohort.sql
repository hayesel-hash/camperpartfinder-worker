-- Playbook initial Jokon 50-row spot-check cohort: keep proposed text in staging.
-- "unreviewed" is intentional: source-page verification is required before accepting.
insert into rv_private.camper_input_quality_batch_v1(batch_label,publisher,catalogue_id,document_sha256,rule_version)
values('jokon-synth-layout-20261124-a','Jokon','independent-v2-9a57a0d831ab419f1a5ee981e533b821',
'94432b574d60e7858a1de5d57dd9ef19dc83c9be9d8a487953b044354667fdc5','synthesised-layout-v5')
on conflict do nothing;
insert into rv_private.camper_input_quality_sample_v1
(batch_label,catalogue_id,document_sha256,page,position,number,proposed_name)
select 'jokon-synth-layout-20261124-a',o.catalogue_id,o.sha256,o.page,o.position,o.number,o.description
from rv_private.master_catalogue_observations o
where o.catalogue_id='independent-v2-9a57a0d831ab419f1a5ee981e533b821'
and o.sha256='94432b574d60e7858a1de5d57dd9ef19dc83c9be9d8a487953b044354667fdc5'
and o.state='staged' and o.description is not null
order by md5(o.number||o.position||o.page::text||'20261124')
limit 50 on conflict do nothing;
insert into rv_private.camper_input_change_log_v1(actor,change_category,reason,details,rollback_instructions)
values('ChatGPT','staging_quality_sample',
'Preserve initial 50-row Jokon naming inspection cohort; German/mixed technical text cannot be assumed to satisfy clean-English naming or page-alignment quality',
jsonb_build_object('batch_label','jokon-synth-layout-20261124-a','source','independent-v2-9a57a0d831ab419f1a5ee981e533b821',
'state','unreviewed','requires','source-page and name-correctness review before promotion'),
'Do not delete cohort; create new versioned batch if rule changes.');
