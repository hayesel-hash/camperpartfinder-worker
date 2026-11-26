-- Supplied-document rows: maker part numbers can be mixed case (RV Designer "Lid-B110", "LidKit200")
-- or two characters long (RV Designer gas props "G1".."G9"). parts.exact_number already allows both.
alter table rv_private.supplied_document_rows_v1 drop constraint if exists supplied_document_rows_v1_number_check;
alter table rv_private.supplied_document_rows_v1 add constraint supplied_document_rows_v1_number_check
  check (number ~ '^[A-Za-z0-9][A-Za-z0-9./-]{1,39}$');
