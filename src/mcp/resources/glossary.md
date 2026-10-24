# Glossário do copiloto

- **Telemetria:** medições enviadas pelos instrumentos da missão ao longo do tempo.
- **Canal:** série de medições de um sensor identificado no conjunto de dados.
- **Anomalia:** comportamento anotado como anormal no benchmark; não confirma uma falha física.
- **Evento raro:** comportamento incomum anotado como nominal, como uma operação planejada.
- **Telecomando:** comando enviado à nave e registrado no conjunto de dados.
- **Baseline:** referência estatística calculada usando apenas o período de treino.
- **MAD:** desvio absoluto mediano, uma medida robusta da variação típica.
- **Score:** valor numérico produzido por um detector; a interpretação depende do detector e do limiar.
- **MCP:** protocolo que permite a um aplicativo disponibilizar ferramentas e contexto a um modelo.
- **Referência nominal:** resumo do comportamento típico calculado com dados de treino.
- **Desvio normalizado:** distância entre o valor observado e a referência, expressa em unidades da variação típica histórica.
- **Canal congelado:** canal que repetiu exatamente o mesmo valor por pelo menos dez leituras seguidas; isso indica um possível problema de medição, não sua causa.
- **Lacuna:** intervalo entre leituras maior que três vezes a cadência esperada.
- **Severidade da qualidade:** graduação do impacto estimado de lacunas, leituras ausentes e canais congelados; não mede a gravidade de uma falha física.
