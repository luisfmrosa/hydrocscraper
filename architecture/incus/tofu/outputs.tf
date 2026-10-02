output "gateway" {
  description = "Bridge gateway: how the containers reach the Incus host (bucket endpoint)."
  value       = local.gateway
}

output "instance_ips" {
  value = var.instance_ips
}

output "quack_port" {
  value = var.quack_port
}

output "bucket_keys" {
  description = "Per-layer S3 credentials, keyed by layer."
  sensitive   = true
  value = {
    for layer, key in incus_storage_bucket_key.layer : layer => {
      bucket     = incus_storage_bucket.layer[layer].name
      access_key = key.access_key
      secret_key = key.secret_key
    }
  }
}
