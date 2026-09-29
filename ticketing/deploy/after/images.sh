# Service images built by the tkt01 service stages (ECR otterworks-demo/ticketing/<svc>:<token>-<shortsha>).
# deploy.sh sources this file; an ORDERS_IMAGE/SEATS_IMAGE/PAYMENTS_IMAGE/CONFIRMATIONS_IMAGE variable
# already set in the environment wins.
: "${ORDERS_IMAGE:=599083837640.dkr.ecr.us-east-1.amazonaws.com/otterworks-demo/ticketing/orders:tkt01-cf0e952b}"
: "${SEATS_IMAGE:=599083837640.dkr.ecr.us-east-1.amazonaws.com/otterworks-demo/ticketing/seats:tkt01-134dbe9c}"
: "${PAYMENTS_IMAGE:=599083837640.dkr.ecr.us-east-1.amazonaws.com/otterworks-demo/ticketing/payments:tkt01-de919223}"
: "${CONFIRMATIONS_IMAGE:=599083837640.dkr.ecr.us-east-1.amazonaws.com/otterworks-demo/ticketing/confirmations:tkt01-71e0ff9415f0}"
