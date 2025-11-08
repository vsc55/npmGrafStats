#!/usr/bin/env bash
# Get Reverse Proxy-Redirection logs

# To better understand the collection with regular expression
# {1,3} get one to three characters. [0-9] character from 0 to 9. \ for special characters. () grouping as an expression. | or
internalips="(10([\.][0-9]{1,3}){3})|(192.168([\.][0-9]{1,3}){2})|(172.(1[6-9]|2[0-9]|3[0-1])([\.][0-9]{1,3}){2})"

# IPv4 regex, format xxx.xxx.xxx.xxx
IPV4_REGEX="([0-9]{1,3}[\.]){3}[0-9]{1,3}"

# IPv6 regex, format xxxx:xxxx:xxxx:xxxx:xxxx:xxxx:xxxx:xxxx
IPV6_REGEX='([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])'

# IPv4 or IPv6 regex
IP_REGEX="($IPV4_REGEX|$IPV6_REGEX)"

# Domain or subdomain, format sub.domain.tld or domain.tld
DOMAIN_REGEX="([a-z0-9\-]*\.){1,3}?[a-z0-9\-]*\.[A-Za-z]{2,6}"

# Get external IP by querying an external service like ifconfig.me
externalip=$(curl -s ifconfig.me/ip)
echo "Your external IP is: $externalip"


monitorfilepath="/monitoringips.txt"
npmhome="/root/.config/NPMGRAF"

# check if monitoringips.txt exists
monitorfile=false
if [ -f "$monitorfilepath" ]
then
    monitorfile=true
fi

# check if ASN DB exists
asndb=false
if [ -f "/geolite/GeoLite2-ASN.mmdb" ]
then
    asndb=true
fi

# Normalize INTERNAL_LOGS and MONITORING_LOGS to uppercase TRUE/FALSE
INTERNAL_LOGS="${INTERNAL_LOGS:-FALSE}"
INTERNAL_LOGS="${INTERNAL_LOGS^^}"

MONITORING_LOGS="${MONITORING_LOGS:-FALSE}"
MONITORING_LOGS="${MONITORING_LOGS^^}"

# extract the N-th IP (1 = first, 2 = second, etc.) from a line
extract_nth_ip() {
    local n="$1"
    local line="$2"
    grep -o -E "$IP_REGEX" <<< "$line" | sed -n "${n}p"
}

# gets all lines including an IP. 
# Grep finds the the IP addresses in the access.log
process_logfile()
{
    local logfile="$1"

    # Now only IPv4 is supported in proxy logs change $IPV4_REGEX to $IP_REGEX to support IPv6
    tail -F "$logfile" | grep --line-buffered -E "$IPV4_REGEX" |
    while IFS= read -r line; do

        # Domain or subdomain gets found.
        targetdomain=$(echo "$line" | grep --line-buffered -m 1 -o -E "$DOMAIN_REGEX" | head -1)
        # targetdomain=$(grep --line-buffered -m 1 -o -E "$DOMAIN_REGEX" <<< "$line") ??????

        # Get the first ip found = outsideip
        # head -1 because grep finds two (sometimes three) and only the first is needed
        outsideip=$(extract_nth_ip 1 "$line")

        # What does outsideip say?
        # [ -z "$outsideip" ] && continue
        


                        # # head -2 and tail -1 because grep finds two (sometimes three) and only the second is needed
                        # targetip=$(extract_nth_ip 2 "$line")

                        # # What does length say? 
                        # # save from 14 postion after space and only the first digits found to length
                        # length=$(echo "$line" | awk -F ' ' '{print $14}' | grep --line-buffered -m 1 -o '[[:digit:]]*')


        # get time from logs
        measurementtime="${line:1:26}"
        #echo "measurement time: $measurementtime"

        #Idea of getting device
        #device=`echo $line | grep -e ""'('*')'""`

        length=""
        targetip=""
        if [[ $outsideip =~ $internalips ]] || [[ $outsideip = $externalip ]]; then
            echo "Internal IP-Source: $outsideip called: $targetdomain"
            script="Internalipinfo.py"
            measurement_name="InternalRProxyIPs"
            enabled="$INTERNAL_LOGS"

        elif $monitorfile && grepcidr -D "$outsideip" "$monitorfilepath" > /dev/null 2>&1; then
            echo "An excluded monitoring service checked: $targetdomain"
            script="Getipinfo.py"
            measurement_name="MonitoringRProxyIPs"
            enabled="$MONITORING_LOGS"

        else
            script="Getipinfo.py"
            measurement_name="Redirections"
            enabled="TRUE"
            length="0"
            targetip="redirect"
        fi

        if [ "$enabled" = "TRUE" ]; then
            cmd=(python "$npmhome/$script" "$outsideip" "$targetdomain" "$length" "$targetip" "$measurement_name" "$measurementtime")

            # only add the asndb argument if script is Getipinfo.py
            if [[ "$script" == "Getipinfo.py" ]]; then
                cmd+=("$asndb")
            fi

            "${cmd[@]}"
        fi
    done
}    

shopt -s nullglob
for logfile in /logs/redirection-host-*_access.log; do
    process_logfile "$logfile" &
done

wait