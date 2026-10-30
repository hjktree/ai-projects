resource "docker_network" "lab" {
  name   = "${var.name_prefix}-network"
  driver = "bridge"
}

resource "docker_volume" "lab" {
  name = "${var.name_prefix}-data"
}

resource "docker_image" "alpine" {
  name         = "alpine:3.22"
  keep_locally = true
}

resource "docker_container" "lab" {
  name  = "${var.name_prefix}-container"
  image = docker_image.alpine.image_id

  command = [
    "sh",
    "-c",
    "while true; do sleep 3600; done"
  ]

  networks_advanced {
    name = docker_network.lab.name
  }

  volumes {
    volume_name    = docker_volume.lab.name
    container_path = "/workspace"
  }

  restart = "no"
}
