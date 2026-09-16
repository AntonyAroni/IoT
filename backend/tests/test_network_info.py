"""
Pruebas del Endpoint de Descubrimiento de Red.

`/api/v1/network/info` llegó con `origin/main` (commit 62fd94b) publicando la enumeración
completa de interfaces de la laptop a cualquiera en la red. Su único consumidor es el tablero de
aula, que solo necesita la dirección de conexión.
"""
import platform
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from backend.api import routes_network
from backend.main import app

IPS_SIMULADAS = [
    {"ip": "192.168.1.50", "type": "Red Wi-Fi / LAN"},
    {"ip": "10.42.0.1", "type": "Zona Wi-Fi (Hotspot de tu Laptop)"},
    {"ip": "172.17.0.1", "type": "Red Interna Docker (No usar)"},
    {"ip": "192.168.56.1", "type": "Red Local / LAN"},
]


class TestNetworkInfoExposure(unittest.TestCase):
    def setUp(self):
        self.local = TestClient(app, client=("127.0.0.1", 50000))
        self.remote = TestClient(app, client=("192.168.1.77", 50000))

    def _info(self, client):
        with mock.patch.object(routes_network, "get_all_host_ips", return_value=list(IPS_SIMULADAS)):
            return client.get("/api/v1/network/info").json()

    def test_local_request_sees_every_interface(self):
        """Quien opera el servidor necesita el detalle para diagnosticar."""
        data = self._info(self.local)
        self.assertEqual(len(data["available_ips"]), len(IPS_SIMULADAS))
        self.assertNotIn("detail_restricted", data)

    def test_remote_request_does_not_enumerate_interfaces(self):
        """Desde la red, enumerar interfaces es reconocimiento que nadie necesita."""
        data = self._info(self.remote)

        self.assertEqual(len(data["available_ips"]), 1)
        self.assertIn("detail_restricted", data)

        expuestas = {item["ip"] for item in data["available_ips"]}
        for oculta in ("172.17.0.1", "192.168.56.1"):
            self.assertNotIn(oculta, expuestas, f"{oculta} no debería publicarse a la red")

    def test_dashboard_still_gets_what_it_needs(self):
        """El tablero se abre desde otras laptops: no puede quedarse sin la dirección."""
        data = self._info(self.remote)

        self.assertEqual(data["status"], "online")
        self.assertTrue(data["primary_ip"])
        for clave in ("web_dashboard", "api_base", "websocket_mobile_template"):
            self.assertIn(clave, data["connection_helpers"])

    def test_hotspot_is_preferred_for_phones(self):
        """Si hay hotspot, es la dirección por la que el móvil debe conectarse."""
        data = self._info(self.remote)
        self.assertEqual(data["primary_ip"], "10.42.0.1")

    def test_docker_networks_are_never_chosen(self):
        solo_docker_y_lan = [
            {"ip": "172.17.0.1", "type": "Red Interna Docker (No usar)"},
            {"ip": "192.168.1.50", "type": "Red Wi-Fi / LAN"},
        ]
        elegida = routes_network.determine_best_client_ip(solo_docker_y_lan)
        self.assertEqual(elegida, "192.168.1.50")


class TestHostnameCommandIsPlatformAware(unittest.TestCase):
    """
    En Windows, `hostname -I` no lista direcciones: interpreta el argumento como el nuevo nombre
    del equipo e intenta cambiarlo. Fallaba y la excepción se capturaba, pero lanzaba un
    subproceso en cada petición y escribía un error por la salida estándar de error.
    """

    def test_no_subprocess_on_windows(self):
        with mock.patch.object(routes_network, "_HOSTNAME_FLAG_IS_SUPPORTED", False):
            with mock.patch.object(routes_network.subprocess, "check_output") as ejecutar:
                routes_network.get_all_host_ips()
        ejecutar.assert_not_called()

    def test_subprocess_used_where_the_flag_means_list(self):
        with mock.patch.object(routes_network, "_HOSTNAME_FLAG_IS_SUPPORTED", True):
            with mock.patch.object(routes_network.subprocess, "check_output",
                                   return_value="10.42.0.1 192.168.1.50\n") as ejecutar:
                ips = routes_network.get_all_host_ips()
        ejecutar.assert_called_once()
        self.assertIn("10.42.0.1", {item["ip"] for item in ips})

    def test_flag_matches_the_running_platform(self):
        self.assertEqual(
            routes_network._HOSTNAME_FLAG_IS_SUPPORTED,
            platform.system() != "Windows"
        )

    def test_socket_enumeration_works_without_external_commands(self):
        """La detección no debe depender de lanzar procesos: debe funcionar en cualquier sistema."""
        with mock.patch.object(routes_network, "_HOSTNAME_FLAG_IS_SUPPORTED", False):
            ips = routes_network.get_all_host_ips()
        self.assertTrue(ips, "Debe detectarse al menos una dirección sin recurrir a subprocesos")
        for item in ips:
            self.assertFalse(item["ip"].startswith("127."), "No se publica la loopback como IP de conexión")


if __name__ == "__main__":
    unittest.main()
