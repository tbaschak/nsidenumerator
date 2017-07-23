#!/usr/bin/env python3

'''
Enumerate DNS servers behind anycast VIPs using the NSID EDNS extension
(RFC 5001)
'''

import argparse
import ipaddress

import dns.query
import dns.message
import dns.resolver
import dns.rdatatype
import dns.rdataclass


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'target', help='The target DNS server.')
    parser.add_argument(
        '-n', '--qname', default='.',
        help='The DNS name to query for. Default: %(default)r')
    parser.add_argument(
        '-t', '--qtype', default='A',
        help='Query type to use. Default: %(default)s')
    parser.add_argument(
        '-c', '--qclass', default='IN', choices=['IN', 'CH'],
        help='Query class to use. Default: %(default)s')
    parser.add_argument(
        '-T', '--timeout', type=float, default=1.,
        help='Timeout before the DNS request expires')
    parser.add_argument('-s', '--sport', type=int, default=12345,
        help='The UDP source port to use for the query. '
        'Default: %(default)s')
    parser.add_argument('-d', '--dport', type=int, default=53,
        help='The UDP destination port to use for the query. '
        'Default: %(default)s')
    parser.add_argument('-e', '--enumerate', type=int,
        help='Enumerate DNS servers using the specified number of paths. '
        'Default: %(default)s')
    parser.add_argument(
        '-I', '--id-server', action='store_true', default=False,
        help='Run a CHAOS TXT id.server. query along with NSID, and match the '
        'answers')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
            help='Print verbose output. Default: %(default)s')
    parser.add_argument('-q', '--quiet', action='store_true', default=False,
            help='Print the minimum necessary information. Default: %(default)s')

    args = parser.parse_args()
    if args.verbose is True and args.quiet is True:
        raise parser.error('--quiet and --verbose are mutually exclusive')
    if args.id_server is True:
        print('Warning: using --id-server overrides qname, qclass and qtype')
        args.qname = 'id.server.'
        args.qtype = 'TXT'
        args.qclass = 'CH'
    return args


def resolve(name, qtype='A'):
    # return the first one, if any. If you want more control, use explicit IPs
    for ans in dns.resolver.query(name, qtype).response.answer:
        return ans.items[0].to_text()
    return ''


def main():
    args = parse_args()
    try:
        ipaddress.ip_address(args.target)
        target = args.target
    except ValueError:
        target = resolve(args.target)
    q = dns.message.make_query(
        args.qname,
        dns.rdatatype.from_text(args.qtype),
        dns.rdataclass.from_text(args.qclass))
    q.use_edns(payload=4096, options=[dns.edns.GenericOption(dns.edns.NSID, b'')])

    start_sport = args.sport
    if args.enumerate is not None:
        if not args.quiet:
            print('Enumerating {} paths'.format(args.enumerate))
        end_sport = start_sport + args.enumerate
    else:
        end_sport = start_sport + 1

    servers = set()
    total_queries = 0
    timeouts = 0
    for sport in range(start_sport, end_sport):
        if args.verbose:
            print('DNS query to {}({}). Qname: {!r}, qtype: {}, '
                'qclass: {}, sport: {}, dport: {}, timeout {}'.format(
                      args.target, target, args.qname, args.qtype, args.qclass,
                      sport, args.dport, args.timeout))
        total_queries += 1
        try:
            response = dns.query.udp(q, target, timeout=args.timeout,
                    source_port=sport, port=args.dport)
        except dns.exception.Timeout:
            timeouts += 1
            continue
        ids = []
        for ans in response.answer:
            for item in ans.items:
                if item.rdtype == dns.rdatatype.TXT and \
                        item.rdclass == dns.rdataclass.CH:
                    ids.append(b''.join(item.strings))
        if len(set(ids)) != 1:
            print('Warning: expected one id.server. response, got {}'.format(
                len(set(ids))))
            id_server = None
        else:
            id_server = ids[0]
        warnings = []
        for opt in response.options:
            if opt.otype == dns.edns.NSID:
                nsid = opt.data
                if args.id_server and id_server and nsid != id_server:
                    warnings.append(
                        'Warning: NSID and id.server differ! '
                        'NSID: {!r}, id.server.: {!r}'.format(
                            nsid, id_server))
                servers.add(nsid)

    hint = '' if len(servers) > 0 else ' (target not supporting NSID?)'
    if not args.quiet:
        print('Found {} servers{}'.format(len(servers), hint))
    for server in sorted(servers):
        print(server)

    if not args.quiet:
        print()
        print('## Statistics')
        print('Total DNS queries      : {}'.format(total_queries))
        print('Timeouts               : {}'.format(timeouts))
        print('Percent failed queries : {:.2f}'.format(
            (timeouts / total_queries) * 100))
        print()
        print('## Warnings')
        if warnings:
            for warning in warnings:
                print('    {}'.format(warning))
        else:
            print('    none')


if __name__ == '__main__':
    main()
