-- Regra do backtest (decisão do usuário, 03/10/2026): um documento só "existe" a partir da
-- data de entrega da versão cujos números estão guardados. Os arquivos da CVM só trazem a
-- última versão; usar a data da 1ª entrega com números de uma reapresentação posterior
-- seria olhar o futuro. Versões coletadas na época (daqui em diante) ficam com a própria data.
CREATE VIEW filing_available AS
SELECT f.id AS filing_id,
       f.doc_type,
       f.cvm_code,
       f.reference_date,
       f.version,
       f.received_date AS available_from,
       first.received_date AS first_received_date
FROM filing f
JOIN LATERAL (
    SELECT min(f1.received_date) AS received_date
    FROM filing f1
    WHERE f1.doc_type = f.doc_type AND f1.cvm_code = f.cvm_code
      AND f1.reference_date = f.reference_date
) first ON true
WHERE f.has_lines;
