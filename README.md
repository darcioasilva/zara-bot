# Zara — Bot do Afrika Restaurante

Bot de atendimento via WhatsApp para o Afrika Restaurante.

## Como atualizar o prato da semana

No painel do Railway, vá em Variables e atualize:
```
PRATO_DA_SEMANA=Polpetone
```

## Variáveis de ambiente necessárias

Ver .env.example

## Tabela no Supabase necessária

```sql
create table pedidos_whatsapp (
  id uuid default gen_random_uuid() primary key,
  telefone text,
  nome_cliente text,
  pedido text,
  criado_em timestamptz,
  status text default 'aguardando'
);
```
