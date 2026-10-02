locals {
  gateway = split("/", var.network_cidr)[0]
}

# ---------------------------------------------------------------------------
# Network and project
# ---------------------------------------------------------------------------

resource "incus_network" "hydroc" {
  name    = var.network_name
  project = "default"
  type    = "bridge"

  config = {
    "ipv4.address" = var.network_cidr
    "ipv4.nat"     = "true"
    "ipv6.address" = "none"
  }
}

resource "incus_project" "hydroc" {
  name        = var.project
  description = "hydrocscraper: DuckLake stack (Postgres catalog, DuckDB quack server, app)"

  config = {
    "features.images"            = "false"
    "features.networks"          = "false"
    "features.profiles"          = "true"
    "features.storage.buckets"   = "true"
    "features.storage.volumes"   = "true"
    "restricted"                 = "true"
    "restricted.devices.nic"     = "managed"
    "restricted.devices.proxy"   = "allow"
    "restricted.networks.access" = incus_network.hydroc.name
  }
}

resource "incus_profile" "hydroc" {
  name    = "hydroc"
  project = incus_project.hydroc.name

  device {
    name = "root"
    type = "disk"
    properties = {
      path = "/"
      pool = var.root_pool
    }
  }
}

# ---------------------------------------------------------------------------
# S3 buckets — one per layer
# ---------------------------------------------------------------------------

resource "incus_storage_bucket" "layer" {
  for_each = var.layers

  name    = "hydroc-${each.key}"
  pool    = var.bucket_pool
  project = incus_project.hydroc.name
}

resource "incus_storage_bucket_key" "layer" {
  for_each = var.layers

  name           = "hydroc-${each.key}-admin"
  pool           = var.bucket_pool
  project        = incus_project.hydroc.name
  storage_bucket = incus_storage_bucket.layer[each.key].name
  role           = "admin"
}

# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------

resource "incus_instance" "node" {
  for_each = var.instance_ips

  name     = each.key
  image    = var.image
  type     = "container"
  project  = incus_project.hydroc.name
  profiles = [incus_profile.hydroc.name]

  device {
    name = "eth0"
    type = "nic"
    properties = {
      network        = incus_network.hydroc.name
      "ipv4.address" = each.value
    }
  }

  dynamic "device" {
    for_each = each.key == "hydroc-duckdb" && var.expose_quack_port > 0 ? [1] : []
    content {
      name = "quack"
      type = "proxy"
      properties = {
        listen  = "tcp:0.0.0.0:${var.expose_quack_port}"
        connect = "tcp:127.0.0.1:${var.quack_port}"
      }
    }
  }
}
