
create or replace function rv_private.camper_finalize_quality_review_v1(p_batch_label text,p_reviewer text)
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare total integer;good integer;pending integer;verdict text;
begin
 if p_reviewer is null or length(btrim(p_reviewer))<3 then
  raise exception 'reviewer required';
 end if;
 perform 1 from rv_private.camper_input_quality_batch_v1
 where batch_label=p_batch_label for update;
 if not found then raise exception 'unknown batch'; end if;
 select count(*),count(*) filter(where accepted is true),
 count(*) filter(where accepted is null)
 into total,good,pending
 from rv_private.camper_input_quality_sample_v1 where batch_label=p_batch_label;
 if total<40 or pending>0 then
   return jsonb_build_object('decision','unreviewed','sampled',total,
                              'not_yet_reviewed',pending,'minimum_required',40);
 end if;
 verdict:=case when good::numeric/total>=0.90 then 'approved' else 'rejected' end;
 update rv_private.camper_input_quality_batch_v1
 set reviewer=p_reviewer,review_completed_at=now(),reviewed_rows=total,
 accepted_rows=good,decision=verdict
 where batch_label=p_batch_label;
 insert into rv_private.camper_input_change_log_v1(actor,change_category,reason,details,rollback_instructions)
 values(p_reviewer,'quality_review_decision','40+ individually marked names assessed against >=90% threshold',
 jsonb_build_object('batch_label',p_batch_label,'accepted',good,
 'sampled',total,'decision',verdict),
 'Maintain original batch evidence; create a NEW batch label if extraction rules change.');
 return jsonb_build_object('decision',verdict,'sampled',total,
                            'accepted',good,'accuracy_pct',round(100.0*good/total,2));
end $fn$;
revoke all on function rv_private.camper_finalize_quality_review_v1(text,text)
from public,anon,authenticated;
insert into rv_private.camper_input_change_log_v1(actor,change_category,reason,details,rollback_instructions)
values('ChatGPT','quality_gate_hardening','Finalise review by counting individual accepted/rejected sample observations, never by trusting self-reported totals',
jsonb_build_object('minimum_samples',40,'minimum_fraction_accepted',0.9,'existing_legacy_publication','not yet wired into this quality gate'),
'Replace or disable the new finalization function; preserve existing source records and sample decisions.');
