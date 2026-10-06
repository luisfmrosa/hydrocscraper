-- Std: NPD monthly field production (tabular, no flattening).
-- Converts one Raw file, given by the runner as the variable raw_file (full
-- s3:// path), to one typed Parquet file in Std with the Raw file's
-- year_month and timestamp:
--   s3://hydroc-std/npd/field_production_monthly/year_month=<ym>/npd_field_production_monthly_<ts>.parquet
-- Keys first, then the other columns; a value that doesn't cast fails the
-- step (data-quality checks go here). Rerunning overwrites the same file.
SET VARIABLE std_file =
    's3://hydroc-std/npd/field_production_monthly/year_month='
    || regexp_extract(getvariable('raw_file'), 'year_month=([^/]+)/', 1)
    || '/npd_field_production_monthly_'
    || regexp_extract(getvariable('raw_file'), '_(\d{8}_\d{4})\.[^./]+$', 1)
    || '.parquet';

COPY (
    SELECT
        prfNpdidInformationCarrier::BIGINT              AS prfNpdidInformationCarrier,
        prfYear::INTEGER                                AS prfYear,
        prfMonth::INTEGER                               AS prfMonth,
        prfInformationCarrier::VARCHAR                  AS prfInformationCarrier,
        prfPrdOilNetMillSm3::DOUBLE                     AS prfPrdOilNetMillSm3,
        prfPrdGasNetBillSm3::DOUBLE                     AS prfPrdGasNetBillSm3,
        prfPrdNGLNetMillSm3::DOUBLE                     AS prfPrdNGLNetMillSm3,
        prfPrdCondensateNetMillSm3::DOUBLE              AS prfPrdCondensateNetMillSm3,
        prfPrdOeNetMillSm3::DOUBLE                      AS prfPrdOeNetMillSm3,
        prfPrdProducedWaterInFieldMillSm3::DOUBLE       AS prfPrdProducedWaterInFieldMillSm3
    FROM hook.raw_views.npd_field_production_monthly
    WHERE ___Raw_filename = getvariable('raw_file')
) TO (getvariable('std_file')) (FORMAT parquet);
