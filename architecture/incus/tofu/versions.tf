terraform {
  required_version = ">= 1.8"

  required_providers {
    incus = {
      source  = "lxc/incus"
      version = "~> 1.0"
    }
  }
}

# Uses the local Incus client configuration (remotes + client certificate);
# no credentials are stored in this repository.
provider "incus" {
  default_remote = var.incus_remote
  config_dir     = var.incus_config_dir
}
