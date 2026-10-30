output "network_name" {
  value = docker_network.lab.name
}

output "volume_name" {
  value = docker_volume.lab.name
}

output "container_name" {
  value = docker_container.lab.name
}

output "image_name" {
  value = docker_image.alpine.name
}
