variable "incus_remote" {
  description = "Incus remote (from the local Incus client config) to deploy to. Set it in terraform.tfvars."
  type        = string
}

variable "incus_config_dir" {
  description = "Incus client config directory. null = provider default ($HOME/.config/incus); on Windows use %APPDATA%\\incus."
  type        = string
  default     = null
}

variable "project" {
  description = "Isolated Incus project for the stack."
  type        = string
  default     = "hydroc"
}

variable "network_name" {
  description = "Dedicated bridge for the stack (created in the default project)."
  type        = string
  default     = "hydroc-br0"
}

variable "network_cidr" {
  description = "Gateway address/prefix of the bridge."
  type        = string
  default     = "10.10.40.1/24"
}

variable "instance_ips" {
  description = "Static IPv4 addresses of the containers."
  type        = map(string)
  default = {
    "hydroc-pg"     = "10.10.40.10"
    "hydroc-duckdb" = "10.10.40.20"
    "hydroc-app"    = "10.10.40.30"
  }
}

variable "image" {
  description = "Image used for every container."
  type        = string
  default     = "images:debian/12"
}

variable "root_pool" {
  description = "Storage pool for container root disks."
  type        = string
  default     = "default"
}

variable "bucket_pool" {
  description = "Storage pool holding the S3 buckets."
  type        = string
  default     = "naspool-buckets"
}

variable "layers" {
  description = "Data layers; each gets a bucket named hydroc-<layer>."
  type        = set(string)
  default     = ["raw", "lake", "library", "dwh", "hook"]
}

variable "quack_port" {
  description = "Port of the DuckDB quack server inside hydroc-duckdb."
  type        = number
  default     = 9494
}

variable "expose_quack_port" {
  description = "Host port to publish the quack server on (0 = not published)."
  type        = number
  default     = 0
}
