import unittest
from datetime import datetime, timedelta
from agentes.verificadores import validar_nif, VerificadorIdentidad, VerificadorVigencia

class TestValidarNIF(unittest.TestCase):
    def test_nif_valido(self):
        self.assertTrue(validar_nif("12345678Z"))

    def test_nif_invalido_letra(self):
        self.assertFalse(validar_nif("12345678A"))

    def test_nif_formato_incorrecto(self):
        self.assertFalse(validar_nif("12345Z"))
        self.assertFalse(validar_nif("ABCDEFGHZ"))

class TestVerificadorIdentidad(unittest.TestCase):
    def setUp(self):
        self.verificador = VerificadorIdentidad()

    def test_identidad_coincide(self):
        texto_doc = "El paciente con NIF 12345678Z ha sido atendido."
        res = self.verificador.validar("12345678Z", texto_doc)
        self.assertTrue(res["valido"])
        self.assertEqual(res["nif_encontrado"], "12345678Z")

    def test_identidad_no_coincide(self):
        texto_doc = "El paciente con NIF 87654321X ha sido atendido."
        res = self.verificador.validar("12345678Z", texto_doc)
        self.assertFalse(res["valido"])
        self.assertEqual(res["nif_encontrado"], "87654321X")

class TestVerificadorVigencia(unittest.TestCase):
    def setUp(self):
        self.verificador = VerificadorVigencia()

    def test_fecha_reciente_valida(self):
        fecha = datetime.now().strftime("%d/%m/%Y")
        texto = f"El documento fue emitido el {fecha}."
        res = self.verificador.validar(texto, "reciente_6_meses")
        self.assertTrue(res["valido"])

    def test_fecha_antigua_invalida(self):
        fecha_antigua = (datetime.now() - timedelta(days=200)).strftime("%d/%m/%Y")
        texto = f"Documento fechado el {fecha_antigua}."
        res = self.verificador.validar(texto, "reciente_6_meses")
        self.assertFalse(res["valido"])

    def test_fecha_futura_alerta(self):
        fecha_futura = (datetime.now() + timedelta(days=10)).strftime("%d/%m/%Y")
        texto = f"Fecha futura: {fecha_futura}."
        res = self.verificador.validar(texto, "reciente_6_meses")
        self.assertFalse(res["valido"])
        self.assertIn("futura", res["detalle"].lower())

if __name__ == "__main__":
    unittest.main()
