package com.otterworks.analytics.repository.iceberg

import com.otterworks.analytics.config.IcebergConfig

import org.apache.hadoop.conf.Configuration
import org.apache.iceberg.{CatalogProperties, CatalogUtil, Table}
import org.apache.iceberg.catalog.{Catalog, Namespace, SupportsNamespaces, TableIdentifier}

import scala.jdk.CollectionConverters.*
import scala.util.Try

/**
 * Builds the Iceberg [[Catalog]] selected by configuration and ensures the
 * analytics events table exists.
 *
 *  - `catalog = "hadoop"` → a filesystem [[org.apache.iceberg.hadoop.HadoopCatalog]]
 *    rooted at `warehouse` (a `file://` path). This needs no AWS and powers the
 *    reconciliation harness and local runs.
 *  - `catalog = "glue"` → an AWS Glue Data Catalog with S3 storage
 *    (`warehouse = s3://<data-lake-bucket>/...`), the cloud "after" target.
 */
object IcebergCatalogFactory:

  def tableIdentifier(config: IcebergConfig): TableIdentifier =
    TableIdentifier.of(Namespace.of(config.database), config.table)

  def create(config: IcebergConfig): Catalog =
    val conf = new Configuration()
    val props =
      if config.isGlueCatalog then
        Map(
          CatalogProperties.CATALOG_IMPL -> "org.apache.iceberg.aws.glue.GlueCatalog",
          CatalogProperties.FILE_IO_IMPL -> "org.apache.iceberg.aws.s3.S3FileIO",
          CatalogProperties.WAREHOUSE_LOCATION -> config.warehouse
        )
      else
        Map(
          CatalogUtil.ICEBERG_CATALOG_TYPE -> CatalogUtil.ICEBERG_CATALOG_TYPE_HADOOP,
          CatalogProperties.WAREHOUSE_LOCATION -> config.warehouse
        )
    CatalogUtil.buildIcebergCatalog("analytics-lakehouse", props.asJava, conf)

  /** Idempotently create the namespace + Iceberg table, then load it. */
  def ensureTable(catalog: Catalog, config: IcebergConfig): Table =
    val id = tableIdentifier(config)
    catalog match
      case ns: SupportsNamespaces =>
        val namespace = Namespace.of(config.database)
        if !ns.namespaceExists(namespace) then Try(ns.createNamespace(namespace))
      case _ => ()
    if catalog.tableExists(id) then catalog.loadTable(id)
    else catalog.createTable(id, IcebergSchema.schema, IcebergSchema.spec)
